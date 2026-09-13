#!/bin/bash
# Fetch secrets from OCI Vault using instance principal authentication
# Writes environment variables to a secure tmpfs file for docker-compose
#
# Required environment variables:
#   OCI_VAULT_OCID     - OCID of the OCI Vault
#   OCI_COMPARTMENT_ID - Compartment OCID where secrets are stored
#
# Optional:
#   OCI_SECRETS_ENV_FILE - Output file path (default: /run/secrets/app.env)
#
# This script requires OCI CLI configured with instance principal:
#   oci setup repair-file-permissions --file /etc/oci/config
#   Or instance principal via dynamic group (no config file needed)

set -euo pipefail

: "${OCI_VAULT_OCID:?OCI_VAULT_OCID is required}"
: "${OCI_COMPARTMENT_ID:?OCI_COMPARTMENT_ID is required}"
: "${OCI_SECRETS_ENV_FILE:=/run/secrets/app.env}"

log() { echo "[$(date -Iseconds)] $*" >&2; }
die() { log "FATAL: $*"; exit 1; }

# Secret name in OCI Vault → environment variable name
declare -A SECRET_MAP=(
    ["portfolio-secret-key"]="SECRET_KEY"
    ["portfolio-postgres-password"]="POSTGRES_PASSWORD"
    ["portfolio-google-client-id"]="GOOGLE_CLIENT_ID"
    ["portfolio-google-client-secret"]="GOOGLE_CLIENT_SECRET"
    ["portfolio-google-redirect-uri"]="GOOGLE_REDIRECT_URI"
    ["portfolio-cumbuca-redirect-uri"]="CUMBUCA_REDIRECT_URI"
    ["portfolio-allowed-emails"]="ALLOWED_GOOGLE_EMAILS"
)

command -v oci >/dev/null 2>&1 || die "OCI CLI not found. Install: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"

log "Creating secure directory for secrets..."
mkdir -p "$(dirname "$OCI_SECRETS_ENV_FILE")"

log "Fetching secrets from OCI Vault..."

secrets_content=""
for secret_name in "${!SECRET_MAP[@]}"; do
    env_var="${SECRET_MAP[$secret_name]}"
    log "  Fetching: $secret_name → $env_var"
    
    secret_ocid=$(oci vault secret list \
        --compartment-id "$OCI_COMPARTMENT_ID" \
        --vault-id "$OCI_VAULT_OCID" \
        --name "$secret_name" \
        --lifecycle-state ACTIVE \
        --auth instance_principal \
        --query 'data[0].id' \
        --raw-output 2>/dev/null) || true
    
    if [[ -z "$secret_ocid" || "$secret_ocid" == "null" ]]; then
        log "  WARNING: Secret '$secret_name' not found, skipping"
        continue
    fi
    
    secret_value=$(oci secrets secret-bundle get \
        --secret-id "$secret_ocid" \
        --auth instance_principal \
        --query 'data."secret-bundle-content".content' \
        --raw-output | base64 -d)
    
    if [[ -n "$secret_value" ]]; then
        secrets_content+="${env_var}=${secret_value}"$'\n'
        log "  OK: $env_var loaded"
    else
        log "  WARNING: Secret '$secret_name' has empty value"
    fi
done

log "Writing secrets to $OCI_SECRETS_ENV_FILE..."
umask 077
echo -n "$secrets_content" > "$OCI_SECRETS_ENV_FILE"
chmod 600 "$OCI_SECRETS_ENV_FILE"

log "Secrets loaded successfully"
