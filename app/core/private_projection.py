from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PrivateProjectionEvent:
    event_id: str
    proposal_id: str
    reviewed_citation: str
    source_revision_id: str
    concept_id: str
    relationship: str


class PrivateStudyProjection(Protocol):
    def apply(self, event: PrivateProjectionEvent) -> None:
        """Apply a connection event exactly once to private study state."""


class InMemoryPrivateStudyProjection:
    """Deterministic private-only projection for tests and local orchestration."""

    def __init__(self) -> None:
        self._applied: set[str] = set()
        self.citations: list[PrivateProjectionEvent] = []
        self.relationships: list[PrivateProjectionEvent] = []

    def apply(self, event: PrivateProjectionEvent) -> None:
        if event.event_id in self._applied:
            return
        self._applied.add(event.event_id)
        self.citations.append(event)
        self.relationships.append(event)
