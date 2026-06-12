from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.core.db import SessionDep
from app.services.prices import refresh_all_exchange_traded_prices
from app.web.navigation import LEGACY_REDIRECTS
from app.web.routes import asset_types, dashboard, investments, securities, snapshots, suggestions

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(asset_types.router)
router.include_router(investments.router)
router.include_router(securities.router)
router.include_router(snapshots.router)
router.include_router(suggestions.router)


@router.post("/prices/refresh")
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
    )
