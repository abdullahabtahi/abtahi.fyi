import pytest
from pathlib import Path
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.web.app import create_app
from app.core.observability import (
    ReleaseVerificationRecord,
    ScheduledOperationOutcome,
    OperationalEvent,
    validate_sanitized_event,
    UnsafeOperationalDataError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

def test_release_verification_record_frozen_and_valid():
    rec = ReleaseVerificationRecord(
        release_revision="rev-001",
        service_url="https://abtahi-fyi-123.us-central1.run.app",
        health_result="ok",
        verified_at=datetime.now(timezone.utc),
    )
    assert rec.release_revision == "rev-001"
    with pytest.raises(Exception):
        rec.health_result = "bad"  # Frozen

def test_scheduled_operation_outcome_valid():
    outcome = ScheduledOperationOutcome(
        operation_id="op-123",
        operation_type="poll_feeds",
        invoker_identity="abtahi-fyi-scheduler@spatial-cat-489006-a4.iam.gserviceaccount.com",
        terminal_status="completed",
        safe_reason="processed_all_feeds",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    assert outcome.terminal_status == "completed"

def test_validate_sanitized_event_rejects_forbidden_fields():
    safe_event = OperationalEvent(
        event_name="readiness_check",
        severity="INFO",
        labels={"revision": "rev-1", "status": "ok"},
        recovery_reference="docs/operations/recovery-guide.md#readiness",
    )
    assert validate_sanitized_event(safe_event) is True

    # Reject private/secret fields
    for forbidden_key in ["body", "request_body", "source_content", "token", "cookie", "secret", "prompt"]:
        unsafe_event = OperationalEvent(
            event_name="request_error",
            severity="ERROR",
            labels={"revision": "rev-1", forbidden_key: "leaked_val"},
            recovery_reference="docs/operations/recovery-guide.md",
        )
        with pytest.raises(UnsafeOperationalDataError):
            validate_sanitized_event(unsafe_event)

def test_request_lifecycle_correlation_id():
    app = create_app(initialize=lambda: None)
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers

def test_monitoring_alert_policies_exist_and_privacy_safe():
    policy_file = REPO_ROOT / "deploy" / "monitoring" / "alert-policies.yaml"
    assert policy_file.is_file(), "deploy/monitoring/alert-policies.yaml must exist"
    content = policy_file.read_text(encoding="utf-8")
    
    # Must declare policies for readiness, scheduled jobs, and 5xx errors
    assert "readiness_unavailable" in content
    assert "privileged_job_failure" in content
    assert "server_5xx_errors" in content
    
    # Must not contain secrets or learner personal tokens
    for prohibited in ["AIza", "password", "session", "csrf_token"]:
        assert prohibited not in content
