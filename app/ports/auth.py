from typing import Protocol, Any, Dict
from datetime import timedelta

class TokenVerifier(Protocol):
    def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        ...

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
        ...

    def verify_session_cookie(self, cookie: str, check_revoked: bool) -> Dict[str, Any]:
        ...
