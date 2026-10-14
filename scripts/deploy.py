#!/usr/bin/env python3
"""Deploy Portfolio Manager with secrets from OCI Vault.

This script fetches secrets from OCI Vault using instance principal authentication
and passes them to docker-compose via environment variables. Secrets are never
written to disk - they exist only in the process environment.

Usage:
    ./scripts/deploy.py up -d --build
    ./scripts/deploy.py down
    ./scripts/deploy.py logs -f app

Any arguments are passed directly to 'docker compose'.

Required environment variables:
    OCI_VAULT_OCID: OCID of the OCI Vault
    OCI_COMPARTMENT_ID: Compartment OCID where secrets are stored

The script requires the OCI Python SDK and instance principal authentication
configured via dynamic group and IAM policy.
"""

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
}

REQUIRED_SECRETS = {"SECRET_KEY", "POSTGRES_PASSWORD", "DATABASE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}


def fetch_vault_secrets() -> dict[str, str]:
    """Fetch secrets from OCI Vault using instance principal."""
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

    for secret_name, env_var in SECRET_MAP.items():
        try:
            secrets_list = vault_client.list_secrets(
                compartment_id=compartment_id,
                vault_id=vault_ocid,
                name=secret_name,
                lifecycle_state="ACTIVE",
            ).data

            if not secrets_list:
                print(f"  {env_var}: not found", file=sys.stderr)
                continue

            secret_id = secrets_list[0].id
            secret_bundle = secrets_client.get_secret_bundle(secret_id=secret_id).data
            content = secret_bundle.secret_bundle_content

            if content.content_type == "BASE64":
                value = base64.b64decode(content.content).decode("utf-8")
            else:
                value = content.content

            secrets[env_var] = value
            print(f"  {env_var}: loaded", file=sys.stderr)
        except Exception as e:
            print(f"  {env_var}: failed ({e})", file=sys.stderr)

    # Check required secrets
    missing = REQUIRED_SECRETS - set(secrets.keys())
    if missing:
        print(f"ERROR: Missing required secrets: {', '.join(sorted(missing))}", file=sys.stderr)
        sys.exit(1)

    return secrets


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    # Fetch secrets from Vault
    secrets = fetch_vault_secrets()

    # Build environment with secrets
    env = os.environ.copy()
    env.update(secrets)

    # Run docker compose with the secrets in environment
    compose_files = [
        "-f", "docker-compose.yml",
        "-f", "docker-compose.production.yml",
    ]

    cmd = ["docker", "compose"] + compose_files + sys.argv[1:]
    print(f"\nRunning: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
