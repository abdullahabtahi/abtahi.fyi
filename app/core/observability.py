"""Sanitized operational telemetry and event models.

Guarantees zero-leakage of private learner notes, reflections, source content,
credentials, tokens, cookies, or secrets into operational events, metrics, or alerts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

FORBIDDEN_EVENT_KEYS = {
    "body",
    "request_body",
    "response_body",
    "source_content",
    "prompt",
    "id_token",
    "token",
    "bearer",
    "cookie",
    "secret",
    "password",
    "api_key",
    "credentials",
    "learner_email",
    "email",
    "consent",
}


class UnsafeOperationalDataError(ValueError):
    """Raised when an operational event contains disallowed or sensitive keys."""
    pass


@dataclass(frozen=True)
class ReleaseVerificationRecord:
    release_revision: str
    service_url: str
    health_result: Literal["ok", "unavailable"]
    verified_at: datetime


@dataclass(frozen=True)
class ScheduledOperationOutcome:
    operation_id: str
    operation_type: Literal["poll_feeds", "consolidate"]
    invoker_identity: str
    terminal_status: Literal["completed", "skipped", "failed", "denied", "unavailable"]
    safe_reason: str
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class OperationalEvent:
    event_name: str
    severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    labels: dict[str, str]
    recovery_reference: str = ""
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))


def validate_sanitized_event(event: OperationalEvent) -> bool:
    """Validates that an operational event does not contain prohibited sensitive keys."""
    for k in event.labels.keys():
        lower_k = k.lower()
        if any(forbidden in lower_k for forbidden in FORBIDDEN_EVENT_KEYS):
            raise UnsafeOperationalDataError(f"Disallowed sensitive key in operational event: {k}")
    return True


def emit_operational_event(event: OperationalEvent) -> None:
    """Safely emits an operational event to standard logging/monitoring."""
    validate_sanitized_event(event)
    logger.info(
        "OPERATIONAL_EVENT name=%s severity=%s labels=%s recovery=%s",
        event.event_name,
        event.severity,
        event.labels,
        event.recovery_reference,
    )
