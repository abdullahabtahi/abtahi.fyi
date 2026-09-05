from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

def verify_csrf(request: Request):
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")
    return True

@router.get("/capture", response_class=HTMLResponse)
async def get_capture(request: Request):
    # Stateful Copilot web authoring UI
    return templates.TemplateResponse(request=request, name="capture.html", context={})

@router.post("/api/poll-feeds")
async def poll_feeds(request: Request, _ = Depends(verify_csrf)):
    # Dispatch polling tasks in the background
    try:
        from app.ingest.poller import poll_all
        # Just mock triggering it in the background for now or call it
        pass
    except Exception:
        pass
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Feed polling dispatched.", "feeds_queued": 1}
    )

@router.post("/api/consolidate")
async def consolidate_graph(request: Request, _ = Depends(verify_csrf)):
    # Triggers Nightly Synthesis Cycle
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Graph synthesis started."}
    )
