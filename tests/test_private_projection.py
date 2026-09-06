import importlib.util


def test_private_projection_module_exists() -> None:
    assert importlib.util.find_spec("app.core.private_projection") is not None


def test_private_projection_applies_event_exactly_once() -> None:
    from app.core.private_projection import (
        InMemoryPrivateStudyProjection,
        PrivateProjectionEvent,
    )

    projection = InMemoryPrivateStudyProjection()
    event = PrivateProjectionEvent(
        event_id="operation-1",
        proposal_id="proposal-1",
        reviewed_citation="Learner-approved citation",
        source_revision_id="source-1",
        concept_id="concept-1",
        relationship="supports",
    )

    projection.apply(event)
    projection.apply(event)

    assert projection.citations == [event]
    assert projection.relationships == [event]
