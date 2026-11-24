"""FastAPI application factory, security middleware, and router registration."""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, closing

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..journal import Journal
from ..locks import exclusive_lock
from ..models import ROOT
from .deps import WebContext, get_all_fleet_directories
from .routers import (
    accounts,
    admin,
    auth,
    bank_angka,
    control,
    cookie_import,
    dashboard,
    notifications,
)

logger = logging.getLogger(__name__)

_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def register_web_routes(app: FastAPI, settings, manager=None, service=None) -> None:
    """Attach WebContext and modular APIRouters to a FastAPI application."""
    registry = (
        manager.registry
        if manager
        else (service.registry if hasattr(service, "registry") else None)
    )
    app.state.web_ctx = WebContext(
        settings=settings,
        registry=registry,
        manager=manager,
        service=service,
    )
    for router_module in (
        cookie_import,
        auth,
        dashboard,
        accounts,
        control,
        notifications,
        admin,
        bank_angka,
    ):
        app.include_router(router_module.router)


def _backfill_existing_journals(ctx: WebContext) -> None:
    directories, _ = get_all_fleet_directories(ctx)
    for directory in dict.fromkeys(directories):
        if (directory / "history.sqlite3").is_file():
            try:
                # Older journals could lack ledger entries. Run the existing backfill before serving read-only queries.
                with closing(Journal(directory)):
                    pass
            except (sqlite3.Error, OSError, ValueError, KeyError, ArithmeticError) as exc:
                logger.warning("Could not backfill account journal (%s)", type(exc).__name__)


def create_app(settings, service=None) -> FastAPI:
    """Create and configure the FastAPI application for control and web dashboard."""
    from ..management import MultiAccountService

    if isinstance(service, MultiAccountService):
        manager = service
        service = None
    else:
        manager = MultiAccountService(settings) if service is None else None
    lifecycle = manager if manager is not None else service
    assert lifecycle is not None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        with exclusive_lock(settings.runtime_dir / "control-server"):
            try:
                await asyncio.to_thread(_backfill_existing_journals, _app.state.web_ctx)
                await lifecycle.start()
                yield
            finally:
                await lifecycle.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/ui", StaticFiles(directory=ROOT / "ojol" / "ui_assets"), name="ui")
    app.state.manager = manager
    app.state.service = service
    app.state.management = manager

    @app.middleware("http")
    async def protect(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": _CSP_HEADER,
            }
        )
        return response

    register_web_routes(app, settings, manager=manager, service=service)
    return app
