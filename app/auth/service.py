from app.ports.auth import TokenVerifier
from app.domain.models import Identity, ForbiddenError

def verify_allowlisted_identity(verifier: TokenVerifier, session_cookie: str, allowed_email: str) -> Identity:
    try:
        claims = verifier.verify_session_cookie(session_cookie, check_revoked=True)
    except Exception as e:
        raise ForbiddenError("Session invalid or expired") from e

    if not claims.get("email_verified"):
        raise ForbiddenError("Email not verified")
    
    if claims.get("email") != allowed_email:
        raise ForbiddenError("Email not allowlisted")

    return Identity(uid=claims["uid"], email=claims["email"])
