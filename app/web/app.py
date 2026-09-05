from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from app.auth.dependencies import auth_router
from app.api.routes_study import study_router
from app.routers.syndication import router as syndication_router
from app.routers.admin import router as admin_router
from app.settings import Settings

def create_app() -> FastAPI:
    settings = Settings()
    
    app = FastAPI(
        title="abtahi.fyi",
        description="Private Compiled Study Pilot",
    )
    
    app.state.settings = settings

    app.include_router(auth_router)
    app.include_router(study_router)
    app.include_router(syndication_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

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
        private_prefixes = ["/study", "/api/study", "/today", "/api/today", "/concepts", "/api/concepts", "/sources", "/api/sources", "/capture", "/api/capture"]
        
        filtered_paths = {}
        for path, path_item in openapi_schema.get("paths", {}).items():
            if not any(path.startswith(prefix) for prefix in private_prefixes):
                filtered_paths[path] = path_item
                
        openapi_schema["paths"] = filtered_paths
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app
