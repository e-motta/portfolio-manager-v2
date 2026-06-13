import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

BACKUP_FOLDER_NAME = "Portfolio Manager Backups"
BACKUP_FILE_PREFIX = "portfolio-backup-"
BACKUP_MIME_TYPE = "application/json"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


@dataclass(frozen=True)
class DriveBackup:
    file_id: str
    name: str
    created_at: datetime
    size_bytes: int


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _parse_drive_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def ensure_backup_folder(access_token: str, folder_id: str | None) -> str:
    if folder_id:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{DRIVE_FILES_URL}/{folder_id}",
                params={"fields": "id,trashed"},
                headers=_auth_headers(access_token),
            )
            if response.status_code == 200 and not response.json().get("trashed"):
                return folder_id

    query = (
        f"name = '{BACKUP_FOLDER_NAME}' and "
        "mimeType = 'application/vnd.google-apps.folder' and "
        "trashed = false"
    )
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            DRIVE_FILES_URL,
            params={"q": query, "fields": "files(id)", "pageSize": 1},
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()
        files = response.json().get("files", [])
        if files:
            return files[0]["id"]

        response = client.post(
            DRIVE_FILES_URL,
            params={"fields": "id"},
            headers=_auth_headers(access_token),
            json={
                "name": BACKUP_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
            },
        )
        response.raise_for_status()
        return response.json()["id"]


def upload_backup(access_token: str, folder_id: str, filename: str, content: bytes) -> DriveBackup:
    metadata = {"name": filename, "parents": [folder_id], "mimeType": BACKUP_MIME_TYPE}
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            DRIVE_UPLOAD_URL,
            params={"uploadType": "multipart", "fields": "id,name,createdTime,size"},
            headers=_auth_headers(access_token),
            files={
                "metadata": ("metadata", json.dumps(metadata), "application/json"),
                "file": (filename, content, BACKUP_MIME_TYPE),
            },
        )
        response.raise_for_status()
        payload = response.json()
        return DriveBackup(
            file_id=payload["id"],
            name=payload["name"],
            created_at=_parse_drive_timestamp(payload["createdTime"]),
            size_bytes=int(payload.get("size", len(content))),
        )


def list_backups(access_token: str, folder_id: str) -> list[DriveBackup]:
    query = f"'{folder_id}' in parents and trashed = false and mimeType = '{BACKUP_MIME_TYPE}'"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            DRIVE_FILES_URL,
            params={
                "q": query,
                "orderBy": "createdTime desc",
                "fields": "files(id,name,createdTime,size)",
                "pageSize": 100,
            },
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()
        backups = []
        for item in response.json().get("files", []):
            backups.append(
                DriveBackup(
                    file_id=item["id"],
                    name=item["name"],
                    created_at=_parse_drive_timestamp(item["createdTime"]),
                    size_bytes=int(item.get("size", 0)),
                )
            )
        return backups


def download_backup(access_token: str, file_id: str) -> bytes:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(
            f"{DRIVE_FILES_URL}/{file_id}",
            params={"alt": "media"},
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()
        return response.content


def delete_backup(access_token: str, folder_id: str, file_id: str) -> None:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{DRIVE_FILES_URL}/{file_id}",
            params={"fields": "parents,mimeType,trashed"},
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("trashed"):
            raise HTTPException(status_code=404, detail="Backup not found.")
        if folder_id not in metadata.get("parents", []):
            raise HTTPException(status_code=404, detail="Backup not found.")
        if metadata.get("mimeType") != BACKUP_MIME_TYPE:
            raise HTTPException(status_code=404, detail="Backup not found.")

        response = client.delete(
            f"{DRIVE_FILES_URL}/{file_id}",
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()


def backup_filename(exported_at: datetime | None = None) -> str:
    timestamp = (exported_at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{BACKUP_FILE_PREFIX}{timestamp}.json"


def raise_drive_error(exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code in {401, 403}:
        raise HTTPException(
            status_code=503,
            detail="Google Drive access expired. Reconnect Google Drive and try again.",
        ) from exc
    raise HTTPException(
        status_code=502,
        detail="Google Drive request failed. Try again in a moment.",
    ) from exc


def drive_call(func, *args: Any, **kwargs: Any):
    try:
        return func(*args, **kwargs)
    except httpx.HTTPStatusError as exc:
        raise_drive_error(exc)
