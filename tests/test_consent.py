from datetime import UTC, datetime, timedelta

import pytest

from app.models.feed import ConsentDecision
from app.services.consent import ConsentService, ConsentUnavailable


class MemoryConsentStore:
    def __init__(self) -> None:
        self.decisions: list[ConsentDecision] = []
        self.available = True

    async def append(self, decision: ConsentDecision) -> None:
        if not self.available:
            raise ConsentUnavailable()
        self.decisions.append(decision)

    async def latest(self, uid: str, revision_id: str, purpose: str, provider: str):
        if not self.available:
            raise ConsentUnavailable()
        matches = [
            decision
            for decision in self.decisions
            if (decision.uid, decision.revision_id, decision.purpose, decision.provider)
            == (uid, revision_id, purpose, provider)
        ]
        return max(matches, key=lambda decision: decision.decided_at) if matches else None


@pytest.mark.asyncio
async def test_consent_requires_an_exact_active_tuple_and_preserves_revocation():
    store = MemoryConsentStore()
    service = ConsentService(store)
    now = datetime.now(UTC)

    await service.record(
        ConsentDecision(
            uid="learner",
            revision_id="revision-1",
            purpose="proposal",
            provider="google-genai",
            granted=True,
            decided_at=now,
        )
    )

    assert await service.has_active_grant("learner", "revision-1", "proposal", "google-genai")
    assert not await service.has_active_grant("learner", "revision-2", "proposal", "google-genai")
    assert not await service.has_active_grant("learner", "revision-1", "summary", "google-genai")

    await service.record(
        ConsentDecision(
            uid="learner",
            revision_id="revision-1",
            purpose="proposal",
            provider="google-genai",
            granted=False,
            decided_at=now + timedelta(seconds=1),
        )
    )

    assert not await service.has_active_grant("learner", "revision-1", "proposal", "google-genai")
