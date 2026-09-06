import logging
import os
import sqlite3
from collections.abc import Callable
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.auth.dependencies import auth_router
from app.api.routes_study import study_router
from app.routers.syndication import router as syndication_router
from app.routers.admin import router as admin_router
from app.core.readiness import ReadinessState
from app.settings import Settings

logger = logging.getLogger(__name__)


def initialize_projection() -> None:
    from app.core.db import init_sqlite_db
    from app.core.network import network_cache
    from app.core.public_loader import PublicContentLoader

    conn = init_sqlite_db()
    conn.close()
    loader = PublicContentLoader()
    items = loader.load_all_items()
    edges = [
        (item.id, out_id, {"type": "reference"})
        for item in items
        for out_id in getattr(item, "outgoing_edges", [])
    ]
    network_cache.initialize(edges)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.initialize_projection()
    except (OSError, RuntimeError, sqlite3.Error) as error:
        app.state.readiness.mark_failed(type(error).__name__)
        logger.error("Projection initialization failed: %s", type(error).__name__)
    else:
        app.state.readiness.mark_ready()

    yield


def create_app(*, initialize: Callable[[], None] | None = None) -> FastAPI:
    settings = Settings()
    
    app = FastAPI(
        title="abtahi.fyi",
        description="Private Compiled Study Pilot",
        lifespan=lifespan
    )
    
    # Mount Static Files
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    app.state.settings = settings
    app.state.initialize_projection = initialize or initialize_projection
    app.state.readiness = ReadinessState()

    app.include_router(auth_router)
    app.include_router(study_router)
    app.include_router(syndication_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        if not app.state.readiness.is_ready:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="abtahi.fyi",
            version="0.1.0",
            description="Private Compiled Study Pilot",
            routes=app.routes,
        )
        
        # Privacy-by-Design Firewall: Filter out all private study routes
        private_prefixes = [
            "/study",
            "/api/study",
            "/today",
            "/api/today",
            "/concepts",
            "/api/concepts",
            "/sources",
            "/api/sources",
            "/capture",
            "/api/capture",
            "/api/proposals",
            "/api/reflections",
            "/api/operations",
            "/api/poll-feeds",
            "/api/consolidate",
        ]
        
        filtered_paths = {}
        for path, path_item in openapi_schema.get("paths", {}).items():
            if not any(path.startswith(prefix) for prefix in private_prefixes):
                filtered_paths[path] = path_item
                
        openapi_schema["paths"] = filtered_paths
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app
