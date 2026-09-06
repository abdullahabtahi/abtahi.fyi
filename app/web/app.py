import logging
import os
import sqlite3
from collections.abc import Callable
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.auth.dependencies import auth_router, auth_pages_router, get_optional_identity
from app.api.routes_study import study_router
from app.routers.syndication import router as syndication_router
from app.routers.api_public import router as api_public_router
from app.routers.admin import router as admin_router
from app.core.readiness import ReadinessState
from app.settings import ConfigurationUnavailable, Settings

logger = logging.getLogger(__name__)


def initialize_projection() -> None:
    from app.core.db import init_sqlite_db
    from app.core.network import network_cache
    from app.core.public_loader import PublicContentLoader

    conn = init_sqlite_db()
    try:
        network_cache.load_curriculum_from_db(conn)
        loader = PublicContentLoader()
        items = loader.load_all_items()
        network_cache.load_from_items(items)
        network_cache.save_snapshot_to_db(conn)
        loader.index_fts(conn, items)
    finally:
        conn.close()


import uuid
from app.core.observability import OperationalEvent, emit_operational_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.initialize_projection()
    except Exception as error:
        app.state.readiness.mark_failed(type(error).__name__)
        logger.error("Projection initialization failed: %s", type(error).__name__)
        emit_operational_event(OperationalEvent(
            event_name="readiness_failed",
            severity="CRITICAL",
            labels={"status": "unavailable", "reason": type(error).__name__},
            recovery_reference="docs/operations/recovery-guide.md#readiness"
        ))
    else:
        app.state.readiness.mark_ready()
        emit_operational_event(OperationalEvent(
            event_name="readiness_ready",
            severity="INFO",
            labels={"status": "ok"}
        ))

    yield


def create_app(*, initialize: Callable[[], None] | None = None) -> FastAPI:
    app = FastAPI(
        title="abtahi.fyi",
        description="Private Compiled Study Pilot",
        lifespan=lifespan
    )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Cloud-Trace-Context") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.middleware("http")
    async def attach_identity_middleware(request: Request, call_next):
        try:
            request.state.identity = get_optional_identity(request)
        except Exception:
            request.state.identity = None
        return await call_next(request)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        if "Cache-Control" not in response.headers:
            path = request.url.path
            if path.startswith("/static/"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif any(
                path.startswith(p)
                for p in [
                    "/study",
                    "/today",
                    "/sources",
                    "/concepts",
                    "/api/study",
                    "/api/today",
                    "/api/sources",
                    "/api/concepts",
                    "/api/proposals",
                    "/api/operations",
                    "/api/reflections",
                ]
            ):
                response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
            elif request.method == "GET" and response.status_code == 200:
                response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"

        return response
    
    # Mount Static Files
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    try:
        app.state.settings = Settings()
    except ConfigurationUnavailable:
        app.state.settings = None
        app.state.configuration_error = True
    else:
        app.state.configuration_error = False
    app.state.initialize_projection = initialize or initialize_projection
    app.state.readiness = ReadinessState()

    app.include_router(auth_router)
    app.include_router(auth_pages_router)
    app.include_router(study_router)
    app.include_router(syndication_router)
    app.include_router(api_public_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    @app.get("/health")
    async def healthz() -> JSONResponse:
        if app.state.configuration_error or not app.state.readiness.is_ready:
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
