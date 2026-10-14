#!/bin/bash
# Remote deployment script for Portfolio Manager
#
# This script is intended to be used as a forced SSH command via:
#   command="/opt/portfolio-manager-v2/scripts/remote-deploy.sh",restrict ssh-ed25519 ...
#
# It receives the image tag via SSH_ORIGINAL_COMMAND, validates it strictly,
# deploys the new version, performs health checks, and automatically rolls
# back if the deployment fails.
#
# Requirements:
#   - /etc/portfolio/deploy.env with OCI_VAULT_OCID and OCI_COMPARTMENT_ID
#   - /opt/portfolio-venv/bin/python with OCI SDK installed
#   - Git repository at /opt/portfolio-manager-v2
#   - Docker and docker-compose installed
#
# Limitations:
#   - Database migrations are NOT rolled back automatically. If a migration
#     causes issues, manual intervention is required.

set -euo pipefail

# Configuration
REPO_DIR="/opt/portfolio-manager-v2"
VENV_PYTHON="/opt/portfolio-venv/bin/python"
DEPLOY_ENV="/etc/portfolio/deploy.env"
DEPLOY_LOG="/opt/portfolio-manager-v2/deploy-history.log"
DEPLOY_LOCK="/var/run/portfolio-deploy.lock"
HEALTH_CHECK_HOST="finance.eduardomotta.dev"
HEALTH_CHECK_TIMEOUT=180  # 3 minutes
HEALTH_CHECK_INTERVAL=5

# Compose files used by deploy.py
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.production.yml)

# Logging
log() {
    local timestamp
    timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    echo "[$timestamp] $*" | tee -a "$DEPLOY_LOG"
}

log_error() {
    log "ERROR: $*" >&2
}

# Validate image tag format (sha-<7-40 hex chars>)
validate_tag() {
    local tag="$1"
    if [[ ! "$tag" =~ ^sha-[0-9a-f]{7,40}$ ]]; then
        log_error "Invalid tag format: '$tag'"
        log_error "Expected format: sha-<7-40 hex characters>"
        exit 1
    fi
}

# Get the app container ID using docker compose
get_app_container_id() {
    cd "$REPO_DIR"
    docker compose "${COMPOSE_FILES[@]}" ps -q app 2>/dev/null || echo ""
}

# Get currently deployed image reference from running container
get_current_image() {
    local container_id
    container_id=$(get_app_container_id)
    if [[ -n "$container_id" ]]; then
        docker inspect --format='{{.Config.Image}}' "$container_id" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Get currently deployed tag from running container
get_current_tag() {
    local image
    image=$(get_current_image)
    if [[ -n "$image" ]]; then
        echo "${image##*:}"
    else
        echo ""
    fi
}

# Get container health status
get_container_health() {
    local container_id
    container_id=$(get_app_container_id)
    if [[ -n "$container_id" ]]; then
        docker inspect --format='{{.State.Health.Status}}' "$container_id" 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# Health check: poll the app until healthy or timeout
health_check() {
    local start_time elapsed
    start_time=$(date +%s)
    
    log "Starting health check (timeout: ${HEALTH_CHECK_TIMEOUT}s)..."
    
    while true; do
        elapsed=$(( $(date +%s) - start_time ))
        
        if (( elapsed >= HEALTH_CHECK_TIMEOUT )); then
            log_error "Health check timed out after ${HEALTH_CHECK_TIMEOUT}s"
            return 1
        fi
        
        local container_health
        container_health=$(get_container_health)
        
        if [[ "$container_health" == "healthy" ]]; then
            # Verify the API endpoint via HTTPS with localhost resolution
            if curl -sf --resolve "${HEALTH_CHECK_HOST}:443:127.0.0.1" \
                    "https://${HEALTH_CHECK_HOST}/api/auth/config" > /dev/null 2>&1; then
                log "Health check passed (container: healthy, API: responding)"
                return 0
            fi
        fi
        
        log "Health check pending (container: ${container_health}, elapsed: ${elapsed}s)..."
        sleep "$HEALTH_CHECK_INTERVAL"
    done
}

# Deploy a specific tag and commit
# Arguments:
#   $1 - image tag (sha-xxx format)
#   $2 - git commit to checkout (optional, defaults to extracting from tag)
deploy_tag() {
    local tag="$1"
    local commit="${2:-}"
    
    # If no commit provided, extract from tag
    if [[ -z "$commit" ]]; then
        commit="${tag#sha-}"
    fi
    
    log "Deploying tag: $tag (commit: $commit)"
    
    cd "$REPO_DIR"
    
    # Checkout the specific commit
    if ! git checkout --detach "$commit" 2>/dev/null; then
        log_error "Cannot checkout commit: $commit"
        return 1
    fi
    
    log "Checked out commit: $(git rev-parse HEAD)"
    
    # Run deploy.py with the tag
    "$VENV_PYTHON" scripts/deploy.py up -d --tag "$tag"
}

# Deploy using a raw image tag (for rollback to non-sha tags like 'latest')
# This doesn't change the git checkout, just sets APP_IMAGE_TAG
deploy_image_tag() {
    local image_tag="$1"
    local git_commit="$2"
    
    log "Deploying image tag: $image_tag (keeping git at: $git_commit)"
    
    cd "$REPO_DIR"
    
    # Checkout the git commit
    if ! git checkout --detach "$git_commit" 2>/dev/null; then
        log_error "Cannot checkout commit: $git_commit"
        return 1
    fi
    
    # Set APP_IMAGE_TAG and run deploy.py
    APP_IMAGE_TAG="$image_tag" "$VENV_PYTHON" scripts/deploy.py up -d --tag "$image_tag"
}

# Perform rollback to previous state
# Arguments:
#   $1 - previous image tag (may be 'latest' or 'sha-xxx')
#   $2 - previous git commit
rollback() {
    local previous_tag="$1"
    local previous_commit="$2"
    
    log "Attempting rollback to tag: $previous_tag, commit: $previous_commit"
    
    if [[ "$previous_tag" =~ ^sha-[0-9a-f]{7,40}$ ]]; then
        # Valid sha tag - use normal deploy
        deploy_tag "$previous_tag" "$previous_commit"
    else
        # Non-sha tag (e.g., 'latest') - deploy with raw image tag
        deploy_image_tag "$previous_tag" "$previous_commit"
    fi
}

# Main deployment logic (runs under flock)
do_deploy() {
    local tag="${SSH_ORIGINAL_COMMAND:-}"
    
    if [[ -z "$tag" ]]; then
        log_error "No command provided (SSH_ORIGINAL_COMMAND is empty)"
        exit 1
    fi
    
    validate_tag "$tag"
    
    local sha="${tag#sha-}"
    
    # Load environment variables (OCIDs, not secrets)
    if [[ -f "$DEPLOY_ENV" ]]; then
        # shellcheck source=/dev/null
        source "$DEPLOY_ENV"
        export OCI_VAULT_OCID OCI_COMPARTMENT_ID
    else
        log_error "Deploy environment file not found: $DEPLOY_ENV"
        exit 1
    fi
    
    cd "$REPO_DIR"
    
    # Fetch main branch and verify the target SHA is on main
    log "Fetching origin/main..."
    git fetch origin main
    
    # Resolve the short SHA to full
    local full_sha
    full_sha=$(git rev-parse "$sha" 2>/dev/null || echo "")
    if [[ -z "$full_sha" ]]; then
        log_error "Cannot resolve commit: $sha"
        exit 1
    fi
    
    # Verify the commit is an ancestor of origin/main
    if ! git merge-base --is-ancestor "$full_sha" origin/main; then
        log_error "Commit $sha is not an ancestor of origin/main"
        log_error "Only commits on the main branch can be deployed"
        exit 1
    fi
    
    log "Verified commit $sha is on main branch"
    
    # Record current state for rollback BEFORE making any changes
    local previous_tag previous_commit
    previous_tag=$(get_current_tag)
    previous_commit=$(git rev-parse HEAD 2>/dev/null || echo "")
    
    log "=========================================="
    log "Starting deployment"
    log "New tag: $tag"
    log "Previous tag: ${previous_tag:-none}"
    log "Previous commit: ${previous_commit:-none}"
    log "=========================================="
    
    # Attempt deployment
    if ! deploy_tag "$tag" "$full_sha"; then
        log_error "Deployment failed"
        
        if [[ -n "$previous_tag" && -n "$previous_commit" ]]; then
            if rollback "$previous_tag" "$previous_commit"; then
                log "Rollback successful"
            else
                log_error "Rollback also failed! Manual intervention required."
            fi
        fi
        
        exit 1
    fi
    
    # Health check
    if ! health_check; then
        log_error "Health check failed for tag: $tag"
        
        if [[ -n "$previous_tag" && -n "$previous_commit" ]]; then
            if rollback "$previous_tag" "$previous_commit" && health_check; then
                log "Rollback successful, previous version is healthy"
            else
                log_error "Rollback failed or unhealthy! Manual intervention required."
            fi
        fi
        
        exit 1
    fi
    
    log "=========================================="
    log "Deployment successful: $tag"
    log "=========================================="
}

# Main entry point with flock
main() {
    # Ensure lock directory exists
    local lock_dir
    lock_dir=$(dirname "$DEPLOY_LOCK")
    if [[ ! -d "$lock_dir" ]]; then
        mkdir -p "$lock_dir" 2>/dev/null || true
    fi
    
    # Use flock to prevent concurrent deploys
    exec 200>"$DEPLOY_LOCK"
    if ! flock -n 200; then
        log_error "Another deployment is in progress (lock: $DEPLOY_LOCK)"
        exit 1
    fi
    
    do_deploy
}

main "$@"
