from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, field_validator, model_validator
import os
import json
from google.cloud import secretmanager


class ConfigurationUnavailable(Exception):
    """Raised when required runtime configuration cannot be loaded safely."""

    def __init__(self, reason: str = "configuration") -> None:
        self.reason = reason
        super().__init__("configuration is unavailable")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True
    )

    GCP_PROJECT_ID: str = Field(...)
    CSRF_SECRET: SecretStr = Field(default=None)
    ALLOWLISTED_EMAIL: str = Field(...)
    FIREBASE_COOKIE_NAME: str = Field(default="session")
    SESSION_EXPIRY_DAYS: int = Field(default=14)
    JOB_AUTH_TOKEN: SecretStr | None = Field(default=None)
    INGESTION_OWNER_UID: str = Field(default="")
    APPROVED_FEED_URLS: str = Field(default="")
    SCHEDULER_SERVICE_ACCOUNT: str = Field(default="")
    SCHEDULER_AUDIENCE: str = Field(default="")
    
    # AI & Core Settings
    GEMINI_API_KEY: str | None = Field(default=None)
    GCP_LOCATION: str = Field(default="us-central1")
    ALLOWED_LEARNER_EMAIL: str = Field(default="")
    PORT: int = Field(default=8000)
    ENV: str = Field(default="production")

    # Firebase Web Client Configuration (loaded from environment or Secret Manager)
    FIREBASE_API_KEY: str = Field(default="")
    FIREBASE_AUTH_DOMAIN: str = Field(default="")
    FIREBASE_PROJECT_ID: str = Field(default="")
    FIREBASE_APP_ID: str = Field(default="")
    FIREBASE_STORAGE_BUCKET: str = Field(default="")

    @model_validator(mode='after')
    def default_firebase_fields(self) -> 'Settings':
        if not self.FIREBASE_PROJECT_ID and self.GCP_PROJECT_ID:
            self.FIREBASE_PROJECT_ID = self.GCP_PROJECT_ID
        if not self.FIREBASE_AUTH_DOMAIN and self.GCP_PROJECT_ID:
            self.FIREBASE_AUTH_DOMAIN = f"{self.GCP_PROJECT_ID}.firebaseapp.com"
        if not self.FIREBASE_STORAGE_BUCKET and self.GCP_PROJECT_ID:
            self.FIREBASE_STORAGE_BUCKET = f"{self.GCP_PROJECT_ID}.firebasestorage.app"
        if not self.FIREBASE_API_KEY and self.GCP_PROJECT_ID == "spatial-cat-489006-a4":
            self.FIREBASE_API_KEY = "AIzaSyAZgvaDjk3S66E2ZRXoeGXJWv9zeJB5Rcg"
        if not self.FIREBASE_APP_ID and self.GCP_PROJECT_ID == "spatial-cat-489006-a4":
            self.FIREBASE_APP_ID = "1:903682941870:web:5dbd7f74136f2e129d5e3f"
        if not self.ALLOWED_LEARNER_EMAIL and self.ALLOWLISTED_EMAIL:
            self.ALLOWED_LEARNER_EMAIL = self.ALLOWLISTED_EMAIL
        return self

    @model_validator(mode='before')
    @classmethod
    def populate_secrets(cls, data: dict) -> dict:
        # Load from env if present
        if 'CSRF_SECRET' not in data and 'CSRF_SECRET' not in os.environ:
            project_id = data.get('GCP_PROJECT_ID') or os.environ.get('GCP_PROJECT_ID')
            if project_id:
                try:
                    client = secretmanager.SecretManagerServiceClient()
                    name = f"projects/{project_id}/secrets/CSRF_SECRET/versions/latest"
                    response = client.access_secret_version(request={"name": name})
                    data['CSRF_SECRET'] = response.payload.data.decode("UTF-8")
                except Exception as error:
                    raise ConfigurationUnavailable() from error
        return data

    @field_validator("SESSION_EXPIRY_DAYS")
    @classmethod
    def check_expiry_bounds(cls, v: int) -> int:
        if not 1 <= v <= 14:
            raise ValueError("SESSION_EXPIRY_DAYS must be between 1 and 14")
        return v
