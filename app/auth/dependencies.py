from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from datetime import timedelta
from secrets import token_urlsafe
from pydantic import BaseModel

from app.ports.auth import TokenVerifier
from app.auth.service import identity_from_claims, verify_allowlisted_identity
from app.adapters.firebase_auth import FirebaseTokenVerifier
from app.domain.models import Identity, ForbiddenError

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# We will need the verifier and settings to be available via dependencies.
# For now, we will define stub dependencies that should be overridden.

def get_token_verifier() -> TokenVerifier:
    return FirebaseTokenVerifier()

def get_allowed_email() -> str:
    from app.settings import Settings
    return Settings().ALLOWLISTED_EMAIL

def require_identity(request: Request, verifier: TokenVerifier = Depends(get_token_verifier), allowed_email: str = Depends(get_allowed_email)) -> Identity:
    session_cookie = request.cookies.get("session")
    if not session_cookie:
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
    session_nonce = request.cookies.get("csrf_nonce")
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing CSRF token")
    if not session_nonce:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing CSRF session")
    
    from app.web.csrf import validate_csrf_token
    if not validate_csrf_token(token, identity.uid, session_nonce, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")
    
    return True

class SessionRequest(BaseModel):
    idToken: str

@auth_router.post("/session")
def create_session(
    payload: SessionRequest, 
    response: Response, 
    verifier: TokenVerifier = Depends(get_token_verifier),
    allowed_email: str = Depends(get_allowed_email),
    csrf_secret: str = Depends(get_csrf_secret),
):
    try:
        identity = identity_from_claims(
            verifier.verify_id_token(payload.idToken), allowed_email
        )
        expires_in = timedelta(days=14)
        cookie = verifier.create_session_cookie(payload.idToken, expires_in=expires_in)
    except (ForbiddenError, ValueError):
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
    csrf_nonce = token_urlsafe(32)
    response.set_cookie(
        key="csrf_nonce",
        value=csrf_nonce,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=int(expires_in.total_seconds()),
        path="/",
    )
    from app.web.csrf import generate_csrf_token
    return {
        "status": "ok",
        "csrfToken": generate_csrf_token(
            identity.uid,
            csrf_nonce,
            csrf_secret,
        ),
    }
