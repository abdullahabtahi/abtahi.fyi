import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from app.core.firestore import (
    IdempotencyConflict,
    ReviewStore,
    ReviewStoreUnavailable,
)
from app.domain.models import (
    DecisionCommand,
    Identity,
    InteractionRecord,
    InteractionType,
    ReviewResult,
)

__all__ = [
    "IdempotencyConflict",
    "ReviewService",
    "ReviewStoreUnavailable",
]


class ReviewService:
    def __init__(
        self,
        store: ReviewStore,
        *,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.new_id = new_id or (lambda: str(uuid.uuid4()))

    async def decide(
        self,
        identity: Identity,
        proposal_id: str,
        command: DecisionCommand,
        key: str,
        *,
        reviewed_content: str | None = None,
    ) -> ReviewResult:
        digest = self._digest(
            {
                "type": InteractionType.PROPOSAL_REVIEW,
                "proposal_id": proposal_id,
                "command": command,
                "reviewed_content": reviewed_content,
            }
        )

        def operation() -> ReviewResult:
            record = InteractionRecord(
                interaction_id=self.new_id(),
                user_id=identity.uid,
                interaction_type=InteractionType.PROPOSAL_REVIEW,
                proposal_id=proposal_id,
                user_decision=command,
                reviewed_content=reviewed_content,
                timestamp=self.now(),
            )
            return ReviewResult(operation_key=key, record=record)

        return await self.store.run_once(identity.uid, key, digest, operation)

    async def reflect(
        self, identity: Identity, reflection_text: str, key: str
    ) -> ReviewResult:
        digest = self._digest(
            {"type": InteractionType.REFLECTION_SUBMIT, "reflection_text": reflection_text}
        )

        def operation() -> ReviewResult:
            record = InteractionRecord(
                interaction_id=self.new_id(),
                user_id=identity.uid,
                interaction_type=InteractionType.REFLECTION_SUBMIT,
                reflection_text=reflection_text,
                timestamp=self.now(),
            )
            return ReviewResult(operation_key=key, record=record)

        return await self.store.run_once(identity.uid, key, digest, operation)

    async def operation_status(
        self, identity: Identity, key: str
    ) -> ReviewResult | None:
        return await self.store.get_operation(identity.uid, key)

    @staticmethod
    def _digest(payload: dict) -> str:
        normalized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
