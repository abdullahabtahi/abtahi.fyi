from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from datetime import timedelta
from pydantic import BaseModel

from app.ports.auth import TokenVerifier
from app.auth.service import verify_allowlisted_identity
from app.domain.models import Identity, ForbiddenError

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# We will need the verifier and settings to be available via dependencies.
# For now, we will define stub dependencies that should be overridden.

def get_token_verifier() -> TokenVerifier:
    class MockVerifier(TokenVerifier):
        def verify_session_cookie(self, session_cookie: str) -> dict:
            return {"uid": "mock-uid", "email": "abdullahabtahi21@gmail.com"}
        def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
            return "mock-session"
    return MockVerifier()

def get_allowed_email() -> str:
    from app.settings import Settings
    return Settings().ALLOWLISTED_EMAIL

def require_identity(request: Request, verifier: TokenVerifier = Depends(get_token_verifier), allowed_email: str = Depends(get_allowed_email)) -> Identity:
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        from app.settings import Settings
        if Settings().ENV == "development":
            return Identity(uid="mock-uid", email=allowed_email)
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/sign-in"})

    try:
        return verify_allowlisted_identity(verifier, session_cookie, allowed_email)
    except ForbiddenError:
        # Check if the request is an API request (JSON expected) or browser request
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/sign-in"})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

def get_csrf_secret() -> str:
    from app.settings import Settings
    return Settings().CSRF_SECRET.get_secret_value()

def require_csrf(
    request: Request, 
    identity: Identity = Depends(require_identity),
    secret: str = Depends(get_csrf_secret)
) -> bool:
    token = request.headers.get("X-CSRF-Token")
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing CSRF token")
    
    from app.web.csrf import validate_csrf_token
    if not validate_csrf_token(token, identity.uid, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")
    
    return True

class SessionRequest(BaseModel):
    idToken: str

@auth_router.post("/session")
def create_session(
    payload: SessionRequest, 
    response: Response, 
    verifier: TokenVerifier = Depends(get_token_verifier)
):
    try:
        expires_in = timedelta(days=14)
        cookie = verifier.create_session_cookie(payload.idToken, expires_in=expires_in)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication failed")

    response.set_cookie(
        key="session",
        value=cookie,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=int(expires_in.total_seconds()),
        path="/"
    )
    return {"status": "ok"}
