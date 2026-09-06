import logging
import firebase_admin
from firebase_admin import auth
from datetime import timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

def ensure_firebase_initialized(project_id: str | None = None) -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        from app.settings import Settings
        settings = Settings()
        pid = project_id or settings.GCP_PROJECT_ID
        logger.info(f"Initializing Firebase Admin with project: {pid}")
        return firebase_admin.initialize_app(options={"projectId": pid})

class FirebaseTokenVerifier:
    def __init__(self, project_id: str | None = None):
        self.app = ensure_firebase_initialized(project_id)

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
        return auth.create_session_cookie(id_token, expires_in=expires_in, app=self.app)

    def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        return auth.verify_id_token(id_token, app=self.app)

    def verify_session_cookie(self, cookie: str, check_revoked: bool) -> Dict[str, Any]:
        return auth.verify_session_cookie(cookie, check_revoked=check_revoked, app=self.app)

