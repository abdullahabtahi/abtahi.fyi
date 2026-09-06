from datetime import datetime, timezone

import pytest

from app.domain.models import (
    ConnectionProposal,
    DecisionCommand,
    DeferredWindow,
    EdgeType,
    Identity,
    MatchStrength,
    ProposalStatus,
)
from app.domain.lifecycle import validate_transition
from app.core.private_projection import InMemoryPrivateStudyProjection


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


def _proposal(status: ProposalStatus = ProposalStatus.PENDING) -> ConnectionProposal:
    return ConnectionProposal(
        id="proposal-1",
        source_revision_id="source-1",
        concept_id="concept-1",
        edge_type=EdgeType.SUPPORTS,
        match_strength=MatchStrength.DIRECT,
        excerpt="Evidence",
        location="Paragraph 1",
        rationale="Relevant",
        uncertainty="Low",
        learning_payoff="Useful",
        proposed_cited_addition="Citation",
        status=status,
    )


def test_defer_requires_window_and_records_derived_due_date() -> None:
    transition = validate_transition(
        _proposal(), DecisionCommand.DEFER, defer_window=DeferredWindow.TOMORROW
    )

    assert transition.proposal is not None
    assert transition.proposal.status is ProposalStatus.DEFERRED
    assert transition.proposal.defer_window is DeferredWindow.TOMORROW
    assert transition.proposal.defer_until is not None


def test_dismissal_can_be_undone_only_with_its_operation_reference() -> None:
    dismissed = validate_transition(
        _proposal(), DecisionCommand.DISMISS, dismissal_operation_id="dismiss-1"
    ).proposal

    restored = validate_transition(
        dismissed, DecisionCommand.UNDO, dismissal_operation_id="dismiss-1"
    ).proposal

    assert restored is not None
    assert restored.status is ProposalStatus.PENDING
    assert restored.revision == 2


class LifecycleReviewStore(InMemoryReviewStore):
    def __init__(self, proposal: ConnectionProposal) -> None:
        super().__init__()
        self.proposal = proposal
        self.events = []

    async def run_proposal_once(
        self, uid, key, digest, proposal_id, operation
    ):
        saved = self.operations.get((uid, key))
        if saved is not None:
            if saved["digest"] != digest:
                from app.services.review import IdempotencyConflict

                raise IdempotencyConflict()
            return saved["result"]
        result, proposal, event = operation(self.proposal)
        self.proposal = proposal
        self.events.append(event) if event is not None else None
        self.operations[(uid, key)] = {"digest": digest, "result": result}
        return result


@pytest.mark.asyncio
async def test_connect_transitions_proposal_and_projects_once() -> None:
    from app.services.review import ReviewService

    store = LifecycleReviewStore(_proposal())
    projection = InMemoryPrivateStudyProjection()
    service = ReviewService(
        store,
        projection=projection,
        now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc),
        new_id=lambda: "interaction-1",
    )
    identity = Identity(uid="learner-1", email="owner@example.com")

    first = await service.decide(
        identity,
        "proposal-1",
        DecisionCommand.CONNECT,
        "operation-1",
        reviewed_content="Learner-approved citation",
    )
    repeated = await service.decide(
        identity,
        "proposal-1",
        DecisionCommand.CONNECT,
        "operation-1",
        reviewed_content="Learner-approved citation",
    )

    assert first == repeated
    assert store.proposal.status is ProposalStatus.CONNECTED
    assert store.proposal.final_reviewed_content == "Learner-approved citation"
    assert len(store.events) == 1
    assert len(projection.citations) == 1
    assert len(projection.relationships) == 1
