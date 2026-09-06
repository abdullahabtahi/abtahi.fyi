from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, field_validator, model_validator
import os
import json
from google.cloud import secretmanager

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
    
    # AI & Core Settings
    GEMINI_API_KEY: str | None = Field(default=None)
    ALLOWED_LEARNER_EMAIL: str = Field(default="abdullah@example.com")
    PORT: int = Field(default=8000)
    ENV: str = Field(default="production")

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
                except Exception:
                    pass # Let pydantic catch the missing field
        return data

    @field_validator("SESSION_EXPIRY_DAYS")
    @classmethod
    def check_expiry_bounds(cls, v: int) -> int:
        if not 1 <= v <= 14:
            raise ValueError("SESSION_EXPIRY_DAYS must be between 1 and 14")
        return v
