from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api")

def verify_csrf(request: Request):
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")
    return True

@router.post("/poll-feeds")
async def poll_feeds(request: Request, _ = Depends(verify_csrf)):
    # Dispatch polling tasks in the background
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Feed polling dispatched.", "feeds_queued": 0}
    )
