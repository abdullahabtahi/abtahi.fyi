from unittest.mock import MagicMock
import pytest
from app.core.firestore import FirestoreConceptStore
from app.domain.models import ConceptNode, CourseModule


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


@pytest.mark.asyncio
async def test_firestore_concept_store_save_and_get(mock_db):
    store = FirestoreConceptStore(mock_db)

    concept = ConceptNode(
        slug="single-points-of-failure",
        title="Single Points of Failure",
        module="M1L1",
        synthesis="Architecture vulnerability notes.",
        summary="A single point of failure disables an entire system.",
        citations=["Citation A"],
        order=1,
    )

    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = concept.model_dump(mode="json")
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_mock

    # Test Save
    await store.save_concept("user-123", concept)
    mock_db.collection.assert_called_with("users")

    # Test Get
    retrieved = await store.get_concept("user-123", "single-points-of-failure")
    assert retrieved is not None
    assert retrieved.slug == "single-points-of-failure"
    assert retrieved.title == "Single Points of Failure"
    assert retrieved.citations == ["Citation A"]


@pytest.mark.asyncio
async def test_firestore_concept_store_list_and_module(mock_db):
    store = FirestoreConceptStore(mock_db)

    module = CourseModule(
        module_id="M1L1",
        title="Complex Systems",
        summary="Test module summary",
    )

    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = module.model_dump(mode="json")
    mock_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [doc_mock]

    await store.save_module("user-123", module)
    modules = await store.list_modules("user-123")

    assert len(modules) == 1
    assert modules[0].module_id == "M1L1"
    assert modules[0].title == "Complex Systems"


@pytest.mark.asyncio
async def test_firestore_concept_store_append_citation(mock_db):
    store = FirestoreConceptStore(mock_db)

    doc_ref = MagicMock()
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"citations": ["Citation 1"]}
    doc_ref.get.return_value = doc_mock
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    await store.append_citation("user-123", "test-concept", "Citation 2")
    doc_ref.update.assert_called_once_with({"citations": ["Citation 1", "Citation 2"]})
