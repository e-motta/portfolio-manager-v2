from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.core.auth import bind_current_user
from app.core.db import SessionDep
from app.services.prices import refresh_all_exchange_traded_prices
from app.web.navigation import LEGACY_REDIRECTS
from app.web.routes import (
    asset_types,
    auth,
    backups,
    dashboard,
    finance,
    investments,
    open_finance,
    securities,
    snapshots,
    suggestions,
)

router = APIRouter()
router.include_router(auth.config_router)
router.include_router(auth.router)

api = APIRouter(prefix="/api", dependencies=[Depends(bind_current_user)])
api.include_router(dashboard.router)
api.include_router(asset_types.router)
api.include_router(investments.router)
api.include_router(securities.router)
api.include_router(snapshots.router)
api.include_router(backups.router)
api.include_router(suggestions.router)
api.include_router(finance.router)
api.include_router(open_finance.router)
router.include_router(api)


@router.post("/api/prices/refresh", dependencies=[Depends(bind_current_user)])
def refresh_prices(session: SessionDep) -> RedirectResponse:
    refresh_all_exchange_traded_prices(session)
    return RedirectResponse(url="/portfolio/holdings", status_code=303)


def _legacy_redirect(target_path: str):
    def _redirect() -> RedirectResponse:
        return RedirectResponse(url=target_path, status_code=301)

    return _redirect


for _legacy_path, _target_path in LEGACY_REDIRECTS.items():
    router.add_api_route(
        _legacy_path,
        _legacy_redirect(_target_path),
        methods=["GET"],
        include_in_schema=False,
        dependencies=[Depends(bind_current_user)],
    )
