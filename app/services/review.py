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
from app.core.private_projection import PrivateProjectionEvent, PrivateStudyProjection
from app.domain.lifecycle import validate_transition
from app.domain.models import (
    ConnectionProposal,
    DecisionCommand,
    DeferredWindow,
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
        projection: PrivateStudyProjection | None = None,
    ) -> None:
        self.store = store
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.new_id = new_id or (lambda: str(uuid.uuid4()))
        self.projection = projection

    async def decide(
        self,
        identity: Identity,
        proposal_id: str,
        command: DecisionCommand,
        key: str,
        *,
        reviewed_content: str | None = None,
        defer_window: DeferredWindow | None = None,
        dismissal_operation_id: str | None = None,
    ) -> ReviewResult:
        digest = self._digest(
            {
                "type": InteractionType.PROPOSAL_REVIEW,
                "proposal_id": proposal_id,
                "command": command,
                "reviewed_content": reviewed_content,
                "defer_window": defer_window,
                "dismissal_operation_id": dismissal_operation_id,
            }
        )

        projection_event: PrivateProjectionEvent | None = None

        def operation(
            proposal: ConnectionProposal | None = None,
        ) -> ReviewResult | tuple[
            ReviewResult, ConnectionProposal, PrivateProjectionEvent | None
        ]:
            nonlocal projection_event
            record = InteractionRecord(
                interaction_id=self.new_id(),
                user_id=identity.uid,
                interaction_type=InteractionType.PROPOSAL_REVIEW,
                proposal_id=proposal_id,
                user_decision=command,
                reviewed_content=reviewed_content,
                timestamp=self.now(),
            )
            result = ReviewResult(operation_key=key, record=record)
            if proposal is None:
                return result
            transition = validate_transition(
                proposal,
                command,
                reviewed_content=reviewed_content,
                defer_window=defer_window,
                dismissal_operation_id=dismissal_operation_id or (
                    key if command is DecisionCommand.DISMISS else None
                ),
                now=self.now(),
            )
            updated_proposal = transition.proposal
            assert updated_proposal is not None
            event = None
            if command is DecisionCommand.CONNECT:
                event = PrivateProjectionEvent(
                    event_id=key,
                    proposal_id=proposal_id,
                    reviewed_citation=updated_proposal.final_reviewed_content or "",
                    source_revision_id=updated_proposal.source_revision_id,
                    concept_id=updated_proposal.concept_id,
                    relationship=updated_proposal.edge_type.value,
                )
            projection_event = event
            return result, updated_proposal, event

        run_proposal_once = getattr(self.store, "run_proposal_once", None)
        if run_proposal_once is None:
            return await self.store.run_once(identity.uid, key, digest, operation)
        result = await run_proposal_once(
            identity.uid, key, digest, proposal_id, operation
        )
        if self.projection is not None and projection_event is not None:
            self.projection.apply(projection_event)
        elif projection_event is not None:
            apply_private_projection = getattr(
                self.store, "apply_private_projection", None
            )
            if apply_private_projection is not None:
                await apply_private_projection(identity.uid, projection_event)
        return result

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

    def reinforce_connection(
        self,
        source_id: str,
        target_id: str,
        boost: float = 0.05,
        network_cache: object | None = None,
    ) -> bool:
        """
        Reinforces an active graph connection cited or approved in study review.
        Boosts edge confidence by +boost (capped at 1.0) and sets last_reinforced_at.
        """
        if network_cache is None:
            from app.core.network import network_cache as default_cache
            cache = default_cache
        else:
            cache = network_cache

        if hasattr(cache, "G") and cache.G.has_edge(source_id, target_id):
            edge_data = cache.G[source_id][target_id]
            curr_conf = float(edge_data.get("confidence", 1.0))
            new_conf = round(min(1.0, curr_conf + boost), 4)
            edge_data["confidence"] = new_conf
            edge_data["last_reinforced_at"] = self.now().isoformat()
            return True
        return False

    @staticmethod
    def _digest(payload: dict) -> str:
        normalized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
