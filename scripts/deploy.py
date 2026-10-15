#!/usr/bin/env python3
"""Deploy Portfolio Manager with secrets from OCI Vault.

This script fetches secrets from OCI Vault using instance principal authentication
and passes them to docker-compose via environment variables. Secrets are never
written to disk - they exist only in the process environment.

Usage:
    ./scripts/deploy.py up -d                 # Pull and deploy latest image
    ./scripts/deploy.py up -d --tag sha-abc   # Deploy specific image tag
    ./scripts/deploy.py up -d --build         # Build locally instead of pulling
    ./scripts/deploy.py down
    ./scripts/deploy.py logs -f app

Options:
    --tag TAG    Image tag to deploy (default: latest). Also sets APP_IMAGE_TAG.
    --build      Build locally instead of pulling from GHCR.

Any other arguments are passed directly to 'docker compose'.

Required environment variables:
    OCI_VAULT_OCID: OCID of the OCI Vault
    OCI_COMPARTMENT_ID: Compartment OCID where secrets are stored

The script requires the OCI Python SDK and instance principal authentication
configured via dynamic group and IAM policy.
"""

import argparse
import base64
import os
import subprocess
import sys

# Secret name in OCI Vault → environment variable name
SECRET_MAP = {
    "portfolio-secret-key": "SECRET_KEY",
    "portfolio-postgres-password": "POSTGRES_PASSWORD",
    "portfolio-database-url": "DATABASE_URL",
    "portfolio-google-client-id": "GOOGLE_CLIENT_ID",
    "portfolio-google-client-secret": "GOOGLE_CLIENT_SECRET",
    "portfolio-google-redirect-uri": "GOOGLE_REDIRECT_URI",
    "portfolio-cumbuca-redirect-uri": "CUMBUCA_REDIRECT_URI",
    "portfolio-allowed-emails": "ALLOWED_GOOGLE_EMAILS",
    "portfolio-pluggy-client-id": "PLUGGY_CLIENT_ID",
    "portfolio-pluggy-client-secret": "PLUGGY_CLIENT_SECRET",
}

REQUIRED_SECRETS = {"SECRET_KEY", "POSTGRES_PASSWORD", "DATABASE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}

GHCR_TOKEN_SECRET = "portfolio-ghcr-token"
GHCR_REGISTRY = "ghcr.io"
GHCR_USERNAME = "e-motta"


def fetch_vault_secrets(include_ghcr: bool = False) -> tuple[dict[str, str], str | None]:
    """Fetch secrets from OCI Vault using instance principal.
    
    Returns:
        Tuple of (secrets dict, ghcr_token or None)
    """
    vault_ocid = os.environ.get("OCI_VAULT_OCID")
    compartment_id = os.environ.get("OCI_COMPARTMENT_ID")

    if not vault_ocid or not compartment_id:
        print("ERROR: OCI_VAULT_OCID and OCI_COMPARTMENT_ID must be set", file=sys.stderr)
        sys.exit(1)

    try:
        from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
        from oci.secrets import SecretsClient
        from oci.vault import VaultsClient
    except ImportError:
        print("ERROR: OCI SDK not installed. Run: pip install oci", file=sys.stderr)
        sys.exit(1)

    print("Authenticating with OCI instance principal...", file=sys.stderr)
    try:
        signer = InstancePrincipalsSecurityTokenSigner()
    except Exception as e:
        print(f"ERROR: Instance principal auth failed: {e}", file=sys.stderr)
        print("Ensure the VM is in a dynamic group with secret-family read policy.", file=sys.stderr)
        sys.exit(1)

    secrets_client = SecretsClient(config={}, signer=signer)
    vault_client = VaultsClient(config={}, signer=signer)

    print("Fetching secrets from OCI Vault...", file=sys.stderr)
    secrets = {}
    ghcr_token = None

    # Build list of secrets to fetch
    secrets_to_fetch = dict(SECRET_MAP)
    if include_ghcr:
        secrets_to_fetch[GHCR_TOKEN_SECRET] = "_GHCR_TOKEN"

    for secret_name, env_var in secrets_to_fetch.items():
        try:
            secrets_list = vault_client.list_secrets(
                compartment_id=compartment_id,
                vault_id=vault_ocid,
                name=secret_name,
                lifecycle_state="ACTIVE",
            ).data

            if not secrets_list:
                if secret_name == GHCR_TOKEN_SECRET:
                    print("  GHCR token: not found (will skip registry login)", file=sys.stderr)
                else:
                    print(f"  {env_var}: not found", file=sys.stderr)
                continue

            secret_id = secrets_list[0].id
            secret_bundle = secrets_client.get_secret_bundle(secret_id=secret_id).data
            content = secret_bundle.secret_bundle_content

            if content.content_type == "BASE64":
                value = base64.b64decode(content.content).decode("utf-8")
            else:
                value = content.content

            if secret_name == GHCR_TOKEN_SECRET:
                ghcr_token = value
                print("  GHCR token: loaded", file=sys.stderr)
            else:
                secrets[env_var] = value
                print(f"  {env_var}: loaded", file=sys.stderr)
        except Exception as e:
            if secret_name == GHCR_TOKEN_SECRET:
                print(f"  GHCR token: failed ({e})", file=sys.stderr)
            else:
                print(f"  {env_var}: failed ({e})", file=sys.stderr)

    # Check required secrets
    missing = REQUIRED_SECRETS - set(secrets.keys())
    if missing:
        print(f"ERROR: Missing required secrets: {', '.join(sorted(missing))}", file=sys.stderr)
        sys.exit(1)

    return secrets, ghcr_token


def docker_login_ghcr(token: str) -> bool:
    """Log in to GHCR using the provided token via stdin.
    
    Returns True if login succeeded.
    """
    print(f"Logging in to {GHCR_REGISTRY}...", file=sys.stderr)
    result = subprocess.run(
        ["docker", "login", GHCR_REGISTRY, "-u", GHCR_USERNAME, "--password-stdin"],
        input=token.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"WARNING: GHCR login failed: {result.stderr.decode()}", file=sys.stderr)
        return False
    print(f"  Logged in to {GHCR_REGISTRY}", file=sys.stderr)
    return True


def docker_logout_ghcr() -> None:
    """Log out from GHCR to remove credentials from ~/.docker/config.json."""
    print(f"Logging out from {GHCR_REGISTRY}...", file=sys.stderr)
    subprocess.run(
        ["docker", "logout", GHCR_REGISTRY],
        capture_output=True,
    )


def parse_args():
    """Parse command-line arguments, extracting deploy.py-specific options."""
    parser = argparse.ArgumentParser(
        description="Deploy Portfolio Manager with OCI Vault secrets",
        add_help=False,
    )
    parser.add_argument("--tag", default="latest", help="Image tag to deploy (default: latest)")
    parser.add_argument("--build", action="store_true", help="Build locally instead of pulling")
    
    # Parse known args, pass the rest to docker compose
    args, docker_args = parser.parse_known_args()
    return args, docker_args


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    args, docker_args = parse_args()
    
    # Determine if we need to pull (need GHCR login)
    needs_pull = not args.build and any(
        cmd in docker_args for cmd in ["up", "pull", "create"]
    )

    # Fetch secrets from Vault
    secrets, ghcr_token = fetch_vault_secrets(include_ghcr=needs_pull)

    # Build environment with secrets
    env = os.environ.copy()
    env.update(secrets)
    env["APP_IMAGE_TAG"] = args.tag

    # Log in to GHCR if we have a token and need to pull
    logged_in = False
    if needs_pull and ghcr_token:
        logged_in = docker_login_ghcr(ghcr_token)

    try:
        # Run docker compose with the secrets in environment
        compose_files = [
            "-f", "docker-compose.yml",
            "-f", "docker-compose.production.yml",
        ]

        # If pulling, do pull first then up without --build
        if needs_pull and "up" in docker_args:
            pull_cmd = ["docker", "compose"] + compose_files + ["pull", "app"]
            print(f"\nPulling image (tag: {args.tag})...", file=sys.stderr)
            print(f"Running: {' '.join(pull_cmd)}", file=sys.stderr)
            pull_result = subprocess.run(pull_cmd, env=env)
            if pull_result.returncode != 0:
                print("ERROR: Failed to pull image", file=sys.stderr)
                sys.exit(pull_result.returncode)

        # Build the docker compose command
        cmd = ["docker", "compose"] + compose_files + docker_args
        
        # Add --build if requested
        if args.build and "up" in docker_args and "--build" not in docker_args:
            cmd.append("--build")
        
        print(f"\nRunning: {' '.join(cmd)}", file=sys.stderr)
        result = subprocess.run(cmd, env=env)
        
    finally:
        # Always log out if we logged in
        # Note: This removes the credential from ~/.docker/config.json
        # Consequence: subsequent `docker pull` without deploy.py will fail
        # for private packages. This is acceptable because:
        # 1. deploy.py is the intended deployment method
        # 2. Leaving credentials on disk is a security risk
        # 3. The package can be made public if passwordless pulls are needed
        if logged_in:
            docker_logout_ghcr()

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
