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
HEALTH_CHECK_URL="http://localhost/api/auth/config"
HEALTH_CHECK_HOST="finance.eduardomotta.dev"
HEALTH_CHECK_TIMEOUT=180  # 3 minutes
HEALTH_CHECK_INTERVAL=5

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

# Get currently deployed tag from running container
get_current_tag() {
    local image
    image=$(docker inspect --format='{{.Config.Image}}' portfolio-manager-v2-app-1 2>/dev/null || echo "")
    if [[ -n "$image" ]]; then
        # Extract tag from image name (e.g., ghcr.io/e-motta/portfolio-manager-v2:sha-abc1234)
        echo "${image##*:}"
    else
        echo ""
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
        
        # Check container health status
        local container_health
        container_health=$(docker inspect --format='{{.State.Health.Status}}' portfolio-manager-v2-app-1 2>/dev/null || echo "unknown")
        
        if [[ "$container_health" == "healthy" ]]; then
            # Also verify the API endpoint
            if curl -sf -H "Host: ${HEALTH_CHECK_HOST}" "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
                log "Health check passed (container: healthy, API: responding)"
                return 0
            fi
        fi
        
        log "Health check pending (container: ${container_health}, elapsed: ${elapsed}s)..."
        sleep "$HEALTH_CHECK_INTERVAL"
    done
}

# Deploy a specific tag
deploy_tag() {
    local tag="$1"
    local sha="${tag#sha-}"
    
    log "Deploying tag: $tag"
    
    # Fetch latest and checkout the commit
    cd "$REPO_DIR"
    git fetch origin
    
    # Try to checkout the specific commit
    if ! git checkout --detach "$sha" 2>/dev/null; then
        # If short SHA doesn't work, try with full resolution
        local full_sha
        full_sha=$(git rev-parse "$sha" 2>/dev/null || echo "")
        if [[ -z "$full_sha" ]]; then
            log_error "Cannot resolve commit: $sha"
            return 1
        fi
        git checkout --detach "$full_sha"
    fi
    
    log "Checked out commit: $(git rev-parse HEAD)"
    
    # Run deploy.py with the tag
    "$VENV_PYTHON" scripts/deploy.py up -d --tag "$tag"
}

# Main deployment logic
main() {
    # Validate SSH_ORIGINAL_COMMAND
    local tag="${SSH_ORIGINAL_COMMAND:-}"
    
    if [[ -z "$tag" ]]; then
        log_error "No command provided (SSH_ORIGINAL_COMMAND is empty)"
        exit 1
    fi
    
    validate_tag "$tag"
    
    # Load environment variables (OCIDs, not secrets)
    if [[ -f "$DEPLOY_ENV" ]]; then
        # shellcheck source=/dev/null
        source "$DEPLOY_ENV"
        export OCI_VAULT_OCID OCI_COMPARTMENT_ID
    else
        log_error "Deploy environment file not found: $DEPLOY_ENV"
        exit 1
    fi
    
    # Record the current tag for potential rollback
    local previous_tag
    previous_tag=$(get_current_tag)
    
    log "=========================================="
    log "Starting deployment"
    log "New tag: $tag"
    log "Previous tag: ${previous_tag:-none}"
    log "=========================================="
    
    # Attempt deployment
    if ! deploy_tag "$tag"; then
        log_error "Deployment failed"
        
        if [[ -n "$previous_tag" ]]; then
            log "Attempting rollback to: $previous_tag"
            if deploy_tag "$previous_tag"; then
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
        
        if [[ -n "$previous_tag" ]]; then
            log "Attempting rollback to: $previous_tag"
            if deploy_tag "$previous_tag" && health_check; then
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

main "$@"
