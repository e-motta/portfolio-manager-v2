import os
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.core.db import SessionDep
from app.models.user import User

SESSION_USER_ID_KEY = "user_id"


def bind_user_to_session(session: Session, user: User) -> None:
    session.info[SESSION_USER_ID_KEY] = user.id


def get_current_user_id(session: Session) -> UUID:
    user_id = session.info.get(SESSION_USER_ID_KEY)
    if user_id is None:
        raise RuntimeError("Not authenticated")
    return user_id


def bind_current_user(request: Request, session: SessionDep) -> User:
    if os.getenv("TESTING") == "1":
        user = session.exec(select(User)).first()
        if not user:
            raise RuntimeError("Test user not seeded")
        request.state.current_user = user
        bind_user_to_session(session, user)
        return user

    raw_id = request.session.get("user_id")
    if not raw_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = session.get(User, UUID(raw_id))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    request.state.current_user = user
    bind_user_to_session(session, user)
    return user


CurrentUserDep = Annotated[User, Depends(bind_current_user)]
