import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.db import init_db, run_migrations
from app.web.middleware import RequireAuthMiddleware
from app.web.router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("TESTING") != "1":
        run_migrations()
        from app.core.db import engine
        from sqlmodel import Session

        with Session(engine) as session:
            init_db(session)
    yield


app = FastAPI(title="Portfolio Manager", lifespan=lifespan)

app.add_middleware(RequireAuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=False,
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.include_router(web_router)
