"""Regression: Pluggy Vault secrets must reach the app container on deploy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deploy_secret_map_includes_optional_pluggy():
    source = (ROOT / "scripts" / "deploy.py").read_text(encoding="utf-8")
    assert '"portfolio-pluggy-client-id": "PLUGGY_CLIENT_ID"' in source
    assert '"portfolio-pluggy-client-secret": "PLUGGY_CLIENT_SECRET"' in source
    required_start = source.index("REQUIRED_SECRETS")
    required_block = source[required_start : source.index("}", required_start)]
    assert "PLUGGY_CLIENT_ID" not in required_block
    assert "PLUGGY_CLIENT_SECRET" not in required_block


def test_compose_files_pass_pluggy_env_to_app():
    for name in ("docker-compose.yml", "docker-compose.production.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "PLUGGY_CLIENT_ID: ${PLUGGY_CLIENT_ID:-}" in text
        assert "PLUGGY_CLIENT_SECRET: ${PLUGGY_CLIENT_SECRET:-}" in text
