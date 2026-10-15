"""OCI Vault secrets integration using instance principal authentication.

Loads secrets from OCI Vault directly into memory at app startup.
No secrets are written to disk.

Required environment variables for production:
    OCI_VAULT_OCID: OCID of the OCI Vault
    OCI_COMPARTMENT_ID: Compartment OCID where secrets are stored

Required OCI IAM configuration:
    - Dynamic group matching the compute instance
    - Policy: Allow dynamic-group <name> to read secret-family in compartment <name>
"""

import base64
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

SECRET_NAME_TO_ENV_VAR: dict[str, str] = {
    "portfolio-secret-key": "SECRET_KEY",
    "portfolio-postgres-password": "POSTGRES_PASSWORD",
    "portfolio-database-url": "DATABASE_URL",
    "portfolio-google-client-id": "GOOGLE_CLIENT_ID",
    "portfolio-google-client-secret": "GOOGLE_CLIENT_SECRET",
    "portfolio-google-redirect-uri": "GOOGLE_REDIRECT_URI",
    "portfolio-cumbuca-redirect-uri": "CUMBUCA_REDIRECT_URI",
    "portfolio-allowed-emails": "ALLOWED_GOOGLE_EMAILS",
    # Pluggy credentials are optional - app starts without them
    "portfolio-pluggy-client-id": "PLUGGY_CLIENT_ID",
    "portfolio-pluggy-client-secret": "PLUGGY_CLIENT_SECRET",
}


class VaultError(Exception):
    """Error fetching secrets from OCI Vault."""


def _get_instance_principal_signer():
    """Get OCI signer using instance principal authentication."""
    try:
        from oci.auth.signers import InstancePrincipalsSecurityTokenSigner

        return InstancePrincipalsSecurityTokenSigner()
    except Exception as e:
        raise VaultError(f"Failed to initialize instance principal auth: {e}") from e


def _fetch_secret_value(
    secrets_client,
    vault_client,
    compartment_id: str,
    vault_id: str,
    secret_name: str,
) -> str | None:
    """Fetch a single secret value from OCI Vault."""
    try:
        secrets_list = vault_client.list_secrets(
            compartment_id=compartment_id,
            vault_id=vault_id,
            name=secret_name,
            lifecycle_state="ACTIVE",
        ).data

        if not secrets_list:
            logger.debug("Secret '%s' not found in vault", secret_name)
            return None

        secret_id = secrets_list[0].id
        secret_bundle = secrets_client.get_secret_bundle(secret_id=secret_id).data
        content = secret_bundle.secret_bundle_content

        if content.content_type == "BASE64":
            return base64.b64decode(content.content).decode("utf-8")
        return content.content
    except Exception as e:
        logger.warning("Failed to fetch secret '%s': %s", secret_name, e)
        return None


REQUIRED_SECRETS = {"SECRET_KEY", "DATABASE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}


@lru_cache(maxsize=1)
def load_vault_secrets() -> dict[str, str]:
    """Load all configured secrets from OCI Vault into memory.

    Returns a dict mapping environment variable names to secret values.
    Only returns secrets that were successfully fetched.

    Raises VaultError if authentication fails or required secrets cannot be loaded.

    This function is cached - secrets are loaded once at startup.
    """
    vault_ocid = os.environ.get("OCI_VAULT_OCID")
    compartment_id = os.environ.get("OCI_COMPARTMENT_ID")

    if not vault_ocid or not compartment_id:
        logger.debug(
            "OCI Vault not configured (OCI_VAULT_OCID and OCI_COMPARTMENT_ID required)"
        )
        return {}

    logger.info("Loading secrets from OCI Vault...")

    try:
        from oci.secrets import SecretsClient
        from oci.vault import VaultsClient

        signer = _get_instance_principal_signer()
        secrets_client = SecretsClient(config={}, signer=signer)
        vault_client = VaultsClient(config={}, signer=signer)
    except ImportError as e:
        raise VaultError(f"OCI SDK not available: {e}") from e

    secrets: dict[str, str] = {}
    for secret_name, env_var in SECRET_NAME_TO_ENV_VAR.items():
        value = _fetch_secret_value(
            secrets_client,
            vault_client,
            compartment_id,
            vault_ocid,
            secret_name,
        )
        if value:
            secrets[env_var] = value
            logger.info("  Loaded: %s", env_var)

    # Check for missing required secrets
    missing = REQUIRED_SECRETS - set(secrets.keys())
    if missing:
        raise VaultError(f"Required secrets not found in Vault: {', '.join(sorted(missing))}")

    logger.info("Loaded %d secrets from OCI Vault", len(secrets))
    return secrets


def get_vault_secret(env_var: str) -> str | None:
    """Get a specific secret value by environment variable name.

    Returns None if the secret is not available.
    """
    return load_vault_secrets().get(env_var)
