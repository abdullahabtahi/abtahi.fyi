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

from app.schemas.synthesis import ConsolidationReport, ConsolidationStatus
from app.ai.synthesis import run_consolidation
from app.core.network import network_cache
from app.core.db import init_sqlite_db

@router.post("/api/consolidate", response_model=ConsolidationReport)
async def consolidate_graph(
    request: Request,
    dry_run: bool = False,
    identity: Identity = Depends(require_identity),
):
    """Triggers Nightly Graph Consolidation ('Dream Cycle').
    
    Supports dry-run queries and returns a full ConsolidationReport.
    Protected by admin authentication / Cloud Scheduler bearer tokens.
    """
    conn = init_sqlite_db()
    try:
        report = await run_consolidation(
            db_conn=conn,
            network_cache=network_cache,
            dry_run=dry_run,
        )
    finally:
        conn.close()

    if report.status == ConsolidationStatus.FAILED:
        return JSONResponse(
            status_code=500,
            content=report.model_dump(mode="json"),
        )
    return JSONResponse(
        status_code=200,
        content=report.model_dump(mode="json"),
    )

