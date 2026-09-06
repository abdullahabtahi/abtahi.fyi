import os
import logging
import hmac
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import timedelta
from secrets import token_urlsafe
from pydantic import BaseModel

from app.ports.auth import TokenVerifier
from app.auth.service import identity_from_claims, verify_allowlisted_identity
from app.adapters.firebase_auth import FirebaseTokenVerifier
from app.domain.models import Identity, ForbiddenError
from app.settings import Settings

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_pages_router = APIRouter(tags=["auth-pages"])

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)

# We will need the verifier and settings to be available via dependencies.
# For now, we will define stub dependencies that should be overridden.

def get_token_verifier() -> TokenVerifier:
    return FirebaseTokenVerifier()

def get_allowed_email() -> str:
    from app.settings import Settings
    return Settings().ALLOWLISTED_EMAIL

def get_optional_identity(
    request: Request,
    verifier: TokenVerifier | None = None,
    allowed_email: str | None = None,
) -> Identity | None:
    """Safely extracts Identity if valid session exists, without raising HTTP exceptions."""
    if hasattr(request, "app"):
        overrides = getattr(request.app, "dependency_overrides", {})
        if get_optional_identity in overrides:
            return overrides[get_optional_identity]()
        if require_identity in overrides:
            return overrides[require_identity]()

    token = request.cookies.get("session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        return None


    try:
        if verifier is None:
            if hasattr(request, "app") and get_token_verifier in getattr(request.app, "dependency_overrides", {}):
                verifier = request.app.dependency_overrides[get_token_verifier]()
            else:
                verifier = get_token_verifier()
        if allowed_email is None:
            if hasattr(request, "app") and get_allowed_email in getattr(request.app, "dependency_overrides", {}):
                allowed_email = request.app.dependency_overrides[get_allowed_email]()
            else:
                allowed_email = get_allowed_email()

        return verify_allowlisted_identity(verifier, token, allowed_email)
    except Exception:
        return None

def require_identity(request: Request, verifier: TokenVerifier = Depends(get_token_verifier), allowed_email: str = Depends(get_allowed_email)) -> Identity:
    token = request.cookies.get("session")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/sign-in"})

    try:
        return verify_allowlisted_identity(verifier, token, allowed_email)
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


class WorkloadTokenVerifier:
    def verify_workload_token(self, token: str, expected_audience: str, expected_principal: str) -> dict:
        from google.oauth2 import id_token
        from google.auth.transport import requests
        
        claims = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=expected_audience if expected_audience else None
        )
        if expected_principal and claims.get("email") != expected_principal:
            raise ValueError(f"Workload principal mismatch: {claims.get('email')}")
        return claims

_default_workload_verifier = WorkloadTokenVerifier()

def get_workload_verifier() -> WorkloadTokenVerifier:
    return _default_workload_verifier


def require_job_identity(request: Request) -> bool:
    """Authorize scheduler/admin jobs via verified Google Cloud OIDC token or configured token."""
    settings = Settings()
    
    # Explicitly reject requests presenting only learner cookies
    provided_token = request.headers.get("X-Job-Token", "")
    if not provided_token:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            provided_token = authorization.split(" ", 1)[1]
            
    if not provided_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing workload authorization")

    # If JOB_AUTH_TOKEN is configured and matches, accept it (for tests/local CLI jobs)
    configured_token = settings.JOB_AUTH_TOKEN
    if configured_token and hmac.compare_digest(provided_token, configured_token.get_secret_value()):
        return True

    # Otherwise verify as Google Cloud OIDC workload token
    expected_aud = settings.SCHEDULER_AUDIENCE
    expected_principal = settings.SCHEDULER_SERVICE_ACCOUNT
    
    verifier = get_workload_verifier()
    if hasattr(request, "app") and get_workload_verifier in getattr(request.app, "dependency_overrides", {}):
        verifier = request.app.dependency_overrides[get_workload_verifier]()

    try:
        claims = verifier.verify_workload_token(
            provided_token,
            expected_audience=expected_aud,
            expected_principal=expected_principal
        )
        request.state.job_identity = claims.get("email") or "workload-service"
        return True
    except Exception as err:
        logger.warning(f"Workload identity verification failed: {err}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

class SessionRequest(BaseModel):
    idToken: str

@auth_router.post("/session")
def create_session(
    payload: SessionRequest, 
    request: Request,
    response: Response, 
    verifier: TokenVerifier = Depends(get_token_verifier),
    allowed_email: str = Depends(get_allowed_email),
    csrf_secret: str = Depends(get_csrf_secret),
):
    try:
        claims = verifier.verify_id_token(payload.idToken)
        identity = identity_from_claims(claims, allowed_email)
        expires_in = timedelta(days=14)
        cookie = verifier.create_session_cookie(payload.idToken, expires_in=expires_in)
    except ForbiddenError:
        logger.warning("Session exchange rejected: identity policy")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="authentication failed"
        )
    except Exception:
        logger.warning("Session exchange rejected: token verification")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="authentication failed"
        )

    expires_in = timedelta(days=Settings().SESSION_EXPIRY_DAYS)
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


@auth_router.post("/logout")
def logout_api(response: Response):
    response.delete_cookie(key="session", path="/")
    response.delete_cookie(key="csrf_nonce", path="/")
    return {"status": "ok"}


@auth_router.get("/config")
def get_auth_client_config():
    from app.settings import Settings
    settings = Settings()
    return {
        "apiKey": settings.FIREBASE_API_KEY,
        "authDomain": settings.FIREBASE_AUTH_DOMAIN,
        "projectId": settings.FIREBASE_PROJECT_ID,
        "appId": settings.FIREBASE_APP_ID,
        "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
    }


@auth_pages_router.get("/sign-in", response_class=HTMLResponse)
async def sign_in_view(request: Request):
    # If learner is already authenticated, redirect directly to /today
    existing_identity = get_optional_identity(request)
    if existing_identity:
        return RedirectResponse(url="/today", status_code=status.HTTP_303_SEE_OTHER)

    from app.settings import Settings
    settings = Settings()
    firebase_config = {
        "apiKey": settings.FIREBASE_API_KEY,
        "authDomain": settings.FIREBASE_AUTH_DOMAIN,
        "projectId": settings.FIREBASE_PROJECT_ID,
        "appId": settings.FIREBASE_APP_ID,
        "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
    }
    return templates.TemplateResponse(
        request=request,
        name="sign_in.html",
        context={"firebase_config": firebase_config},
    )


@auth_pages_router.get("/logout")
def logout_redirect(response: Response):
    redirect = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="session", path="/")
    redirect.delete_cookie(key="csrf_nonce", path="/")
    return redirect


@auth_pages_router.get("/dev-login")
async def dev_login_view(request: Request, redirect_to: str = "/study"):
    import os
    if os.environ.get("K_SERVICE"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    from secrets import token_urlsafe

    redirect = RedirectResponse(url=redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="session",
        value="local-dev-session",
        httponly=True,
        samesite="lax",
        path="/",
    )
    redirect.set_cookie(
        key="csrf_nonce",
        value=token_urlsafe(32),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return redirect
