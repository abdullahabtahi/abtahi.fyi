from datetime import datetime, timezone

import pytest

from app.domain.models import DecisionCommand, Identity


class InMemoryReviewStore:
    def __init__(self) -> None:
        self.operations = {}

    async def run_once(self, uid, key, digest, operation):
        saved = self.operations.get((uid, key))
        if saved is not None:
            if saved["digest"] != digest:
                from app.services.review import IdempotencyConflict

                raise IdempotencyConflict()
            return saved["result"]
        result = operation()
        self.operations[(uid, key)] = {"digest": digest, "result": result}
        return result

    async def get_operation(self, uid, key):
        saved = self.operations.get((uid, key))
        return saved["result"] if saved else None


@pytest.mark.asyncio
async def test_same_key_returns_original_decision_result() -> None:
    from app.services.review import ReviewService

    service = ReviewService(
        InMemoryReviewStore(),
        now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc),
        new_id=lambda: "interaction-1",
    )
    identity = Identity(uid="learner-1", email="owner@example.com")

    first = await service.decide(
        identity, "proposal-1", DecisionCommand.CONNECT, "operation-1"
    )
    repeated = await service.decide(
        identity, "proposal-1", DecisionCommand.CONNECT, "operation-1"
    )

    assert repeated == first
    assert first.record.user_decision is DecisionCommand.CONNECT
    assert first.record.timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_key_reuse_with_a_different_decision_is_rejected() -> None:
    from app.services.review import IdempotencyConflict, ReviewService

    service = ReviewService(InMemoryReviewStore())
    identity = Identity(uid="learner-1", email="owner@example.com")

    await service.decide(identity, "proposal-1", DecisionCommand.CONNECT, "operation-1")

    with pytest.raises(IdempotencyConflict):
        await service.decide(
            identity, "proposal-1", DecisionCommand.DISMISS, "operation-1"
        )
