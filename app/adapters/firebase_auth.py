import firebase_admin
from firebase_admin import auth
from datetime import timedelta
from typing import Dict, Any

class FirebaseTokenVerifier:
    def __init__(self):
        # We assume firebase_admin has been initialized elsewhere (e.g. at startup)
        pass

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
        return auth.create_session_cookie(id_token, expires_in=expires_in)

    def verify_session_cookie(self, cookie: str, check_revoked: bool) -> Dict[str, Any]:
        return auth.verify_session_cookie(cookie, check_revoked=check_revoked)
