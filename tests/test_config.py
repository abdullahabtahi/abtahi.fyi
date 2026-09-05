import pytest
import os
from pydantic import ValidationError
from app.settings import Settings

@pytest.fixture(autouse=True)
def clean_env():
    old = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.clear()
    os.environ.update(old)

def test_settings_requires_gcp_project_id():
    os.environ["CSRF_SECRET"] = "super_secret_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "GCP_PROJECT_ID" in str(exc_info.value)

def test_settings_hides_secrets_from_repr():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    settings = Settings()
    
    assert "super_secret_value" not in repr(settings)
    assert "super_secret_value" not in str(settings)
    assert settings.CSRF_SECRET.get_secret_value() == "super_secret_value"

def test_settings_rejects_unknown_fields():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    
    with pytest.raises(ValidationError) as exc_info:
        Settings(UNKNOWN_FIELD="bad")
    assert "Extra inputs are not permitted" in str(exc_info.value)

def test_secret_provider_env_fallback():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "env_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    s = Settings()
    assert s.CSRF_SECRET.get_secret_value() == "env_value"

def test_secret_values_not_in_validation_errors():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    # Missing required ALLOWLISTED_EMAIL
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "super_secret_value" not in str(exc_info.value)

def test_settings_valid_config_succeeds():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    settings = Settings()
    assert settings.GCP_PROJECT_ID == "test-project"
    assert settings.ALLOWLISTED_EMAIL == "owner@example.com"

def test_settings_missing_nonscret_field_names_field():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "ALLOWLISTED_EMAIL" in str(exc_info.value)

def test_settings_session_expiry_bounds():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["CSRF_SECRET"] = "super_secret_value"
    os.environ["ALLOWLISTED_EMAIL"] = "owner@example.com"
    
    os.environ["SESSION_EXPIRY_DAYS"] = "15"
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "SESSION_EXPIRY_DAYS must be between 1 and 14" in str(exc_info.value)
    
    os.environ["SESSION_EXPIRY_DAYS"] = "0"
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "SESSION_EXPIRY_DAYS must be between 1 and 14" in str(exc_info.value)
    
    os.environ["SESSION_EXPIRY_DAYS"] = "10"
    settings = Settings()
    assert settings.SESSION_EXPIRY_DAYS == 10
