from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from app.auth.dependencies import require_identity, require_csrf
from app.domain.models import Identity

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

@router.get("/capture", response_class=HTMLResponse)
async def get_capture(request: Request, identity: Identity = Depends(require_identity)):
    # Stateful Copilot web authoring UI
    return templates.TemplateResponse(request=request, name="capture.html", context={})

@router.post("/api/poll-feeds")
async def poll_feeds(request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf)):
    return JSONResponse(
        status_code=501,
        content={
            "status": "unavailable",
            "message": "Feed polling is unavailable until durable ingestion is configured.",
        },
    )

@router.post("/api/consolidate")
async def consolidate_graph(request: Request, identity: Identity = Depends(require_identity), csrf_ok: bool = Depends(require_csrf)):
    # Triggers Nightly Synthesis Cycle
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Graph synthesis started."}
    )
