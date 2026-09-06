from app.ports.auth import TokenVerifier
from app.domain.models import Identity, ForbiddenError

def identity_from_claims(claims: dict, allowed_email: str) -> Identity:
    if not claims.get("email_verified"):
        raise ForbiddenError("Email not verified")
    claims_email = (claims.get("email") or "").strip().lower()
    target_email = allowed_email.strip().lower()
    if not claims_email or claims_email != target_email:
        raise ForbiddenError(f"Email '{claims.get('email')}' is not allowlisted")
    uid = claims.get("uid")
    if not uid:
        raise ForbiddenError("Identity missing uid")
    return Identity(uid=uid, email=claims["email"])

def verify_allowlisted_identity(verifier: TokenVerifier, session_cookie: str, allowed_email: str) -> Identity:
    try:
        claims = verifier.verify_session_cookie(session_cookie, check_revoked=True)
    except Exception as e:
        raise ForbiddenError("Session invalid or expired") from e

    return identity_from_claims(claims, allowed_email)
