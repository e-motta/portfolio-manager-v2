from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from app.models.user import User
from app.services.google_drive import drive_call, ensure_backup_folder
from app.services.google_oauth import refresh_access_token

OAUTH_PURPOSE_DRIVE = "drive"


def complete_drive_connection(session: Session, user: User, token: dict) -> None:
    refresh_token = token.get("refresh_token")
    if refresh_token:
        user.google_refresh_token = refresh_token
        session.add(user)
        session.commit()
        session.refresh(user)

    if not user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google did not return a refresh token. Try again.",
        )

    access_token = refresh_access_token(user.google_refresh_token)
    folder_id = drive_call(
        ensure_backup_folder, access_token, user.google_drive_folder_id
    )
    user.google_drive_folder_id = folder_id
    session.add(user)
    session.commit()


def get_logged_in_user(session: Session, user_id: str | None) -> User:
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = session.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
