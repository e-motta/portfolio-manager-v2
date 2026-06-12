import httpx
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

from app.core.config import settings

config = Config(
    environ={
        "GOOGLE_CLIENT_ID": settings.GOOGLE_CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": settings.GOOGLE_CLIENT_SECRET,
    }
)
oauth = OAuth(config)
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
LOGIN_SCOPES = "openid email profile"
DRIVE_SCOPES = f"{LOGIN_SCOPES} {DRIVE_SCOPE}"


def refresh_access_token(refresh_token: str) -> str:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]
