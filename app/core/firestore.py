import asyncio
from collections.abc import Callable
from typing import Protocol

from google.cloud.firestore_v1 import transactional

from app.core.private_projection import PrivateProjectionEvent
from app.domain.models import ConnectionProposal, ReviewResult, ConceptNode, CourseModule
from app.models.feed import ConsentDecision, SourceRevision
from app.services.consent import ConsentUnavailable
from app.services.ingestion import SourceMetadataStore


class ReviewStoreError(Exception):
    """Base exception for an unavailable or conflicted review operation."""


class IdempotencyConflict(ReviewStoreError):
    """The operation key was already used for a different request."""


class ReviewStoreUnavailable(ReviewStoreError):
    """The durable review store could not complete an operation."""


class ReviewStore(Protocol):
    async def run_once(
        self,
        uid: str,
        key: str,
        digest: str,
        operation: Callable[[], ReviewResult],
    ) -> ReviewResult:
        ...

    async def get_operation(self, uid: str, key: str) -> ReviewResult | None:
        ...

    async def get_pending_proposals(
        self, uid: str, limit: int = 3
    ) -> list[ConnectionProposal]:
        ...

    async def run_proposal_once(
        self,
        uid: str,
        key: str,
        digest: str,
        proposal_id: str,
        operation: Callable[
            [ConnectionProposal],
            tuple[ReviewResult, ConnectionProposal, PrivateProjectionEvent | None],
        ],
    ) -> ReviewResult:
        ...

    async def apply_private_projection(
        self, uid: str, event: PrivateProjectionEvent
    ) -> None:
        ...


class FirestoreReviewStore:
    def __init__(self, db_client) -> None:
        self.db = db_client

    def _operation_ref(self, uid: str, key: str):
        return (
            self.db.collection("users")
            .document(uid)
            .collection("operations")
            .document(key)
        )

    def _interactions_ref(self, uid: str, interaction_id: str):
        return (
            self.db.collection("users")
            .document(uid)
            .collection("interactions")
            .document(interaction_id)
        )

    def _proposal_ref(self, uid: str, proposal_id: str):
        return (
            self.db.collection("users")
            .document(uid)
            .collection("proposals")
            .document(proposal_id)
        )

    def _projection_event_ref(self, uid: str, event_id: str):
        return (
            self.db.collection("users")
            .document(uid)
            .collection("private_projection_events")
            .document(event_id)
        )

    async def run_once(
        self,
        uid: str,
        key: str,
        digest: str,
        operation: Callable[[], ReviewResult],
    ) -> ReviewResult:
        try:
            return await asyncio.to_thread(
                self._run_once_sync, uid, key, digest, operation
            )
        except ReviewStoreError:
            raise
        except Exception as error:
            raise ReviewStoreUnavailable("review storage is unavailable") from error

    def _run_once_sync(
        self,
        uid: str,
        key: str,
        digest: str,
        operation: Callable[[], ReviewResult],
    ) -> ReviewResult:
        operation_ref = self._operation_ref(uid, key)
        transaction = self.db.transaction()

        @transactional
        def save_once(transaction):
            existing = operation_ref.get(transaction=transaction)
            if existing.exists:
                saved = existing.to_dict()
                if saved["digest"] != digest:
                    raise IdempotencyConflict("idempotency key was reused")
                return saved["result"]

            result = operation()
            transaction.set(
                operation_ref,
                {
                    "digest": digest,
                    "status": result.status,
                    "result": result.model_dump(mode="json"),
                },
            )
            transaction.set(
                self._interactions_ref(uid, result.record.interaction_id),
                result.record.model_dump(mode="json"),
            )
            return result.model_dump(mode="json")

        return ReviewResult.model_validate(save_once(transaction))

    async def get_operation(self, uid: str, key: str) -> ReviewResult | None:
        try:
            data = await asyncio.to_thread(self._get_operation_sync, uid, key)
        except Exception as error:
            raise ReviewStoreUnavailable("review storage is unavailable") from error
        return ReviewResult.model_validate(data["result"]) if data else None

    async def run_proposal_once(
        self,
        uid: str,
        key: str,
        digest: str,
        proposal_id: str,
        operation: Callable[
            [ConnectionProposal],
            tuple[ReviewResult, ConnectionProposal, PrivateProjectionEvent | None],
        ],
    ) -> ReviewResult:
        try:
            return await asyncio.to_thread(
                self._run_proposal_once_sync,
                uid,
                key,
                digest,
                proposal_id,
                operation,
            )
        except ReviewStoreError:
            raise
        except ValueError:
            raise
        except Exception as error:
            raise ReviewStoreUnavailable("review storage is unavailable") from error

    def _run_proposal_once_sync(
        self,
        uid: str,
        key: str,
        digest: str,
        proposal_id: str,
        operation: Callable[
            [ConnectionProposal],
            tuple[ReviewResult, ConnectionProposal, PrivateProjectionEvent | None],
        ],
    ) -> ReviewResult:
        operation_ref = self._operation_ref(uid, key)
        proposal_ref = self._proposal_ref(uid, proposal_id)
        transaction = self.db.transaction()

        @transactional
        def save_once(transaction):
            existing = operation_ref.get(transaction=transaction)
            if existing.exists:
                saved = existing.to_dict()
                if saved["digest"] != digest:
                    raise IdempotencyConflict("idempotency key was reused")
                return saved["result"]
            proposal_document = proposal_ref.get(transaction=transaction)
            if not proposal_document.exists:
                raise ValueError("proposal not found")
            result, proposal, event = operation(
                ConnectionProposal.model_validate(proposal_document.to_dict())
            )
            transaction.set(proposal_ref, proposal.model_dump(mode="json"))
            transaction.set(
                operation_ref,
                {
                    "digest": digest,
                    "status": result.status,
                    "result": result.model_dump(mode="json"),
                },
            )
            transaction.set(
                self._interactions_ref(uid, result.record.interaction_id),
                result.record.model_dump(mode="json"),
            )
            if event is not None:
                transaction.set(
                    self._projection_event_ref(uid, event.event_id),
                    {"status": "pending", "event": event.__dict__},
                )
            return result.model_dump(mode="json")

        return ReviewResult.model_validate(save_once(transaction))

    async def apply_private_projection(
        self, uid: str, event: PrivateProjectionEvent
    ) -> None:
        try:
            await asyncio.to_thread(self._apply_private_projection_sync, uid, event)
        except Exception as error:
            raise ReviewStoreUnavailable("review storage is unavailable") from error

    def _apply_private_projection_sync(
        self, uid: str, event: PrivateProjectionEvent
    ) -> None:
        event_ref = self._projection_event_ref(uid, event.event_id)
        transaction = self.db.transaction()

        @transactional
        def apply_once(transaction):
            saved = event_ref.get(transaction=transaction)
            if not saved.exists:
                raise ReviewStoreUnavailable("projection event is unavailable")
            if saved.to_dict().get("status") == "applied":
                return
            base = self.db.collection("users").document(uid).collection("private_study")
            transaction.set(
                base.collection("citations").document(event.event_id),
                event.__dict__,
            )
            transaction.set(
                base.collection("relationships").document(event.event_id),
                event.__dict__,
            )
            transaction.update(event_ref, {"status": "applied"})

        apply_once(transaction)

    def _get_operation_sync(self, uid: str, key: str) -> dict | None:
        document = self._operation_ref(uid, key).get()
        return document.to_dict() if document.exists else None

    async def get_pending_proposals(
        self, uid: str, limit: int = 3
    ) -> list[ConnectionProposal]:
        try:
            documents = await asyncio.to_thread(self._get_pending_proposals_sync, uid, limit)
        except Exception as error:
            raise ReviewStoreUnavailable("review storage is unavailable") from error
        return [ConnectionProposal.model_validate(document) for document in documents]

    def _get_pending_proposals_sync(self, uid: str, limit: int) -> list[dict]:
        documents = (
            self.db.collection("users")
            .document(uid)
            .collection("proposals")
            .where("status", "==", "PENDING")
            .limit(limit)
            .stream()
        )
        return [document.to_dict() for document in documents]


class FirestoreSourceConsentStore:
    def __init__(self, db_client) -> None:
        self.db = db_client

    def has_external_model_consent(self, source_revision_id: str) -> bool:
        document = (
            self.db.collection("source_revisions")
            .document(source_revision_id)
            .collection("consents")
            .document("external_model")
            .get()
        )
        return document.exists and document.to_dict().get("granted") is True


class FirestoreConsentStore:
    """Append-only consent ledger scoped under the verified learner path."""

    def __init__(self, db_client) -> None:
        self.db = db_client

    def _decisions(self, uid: str):
        return self.db.collection("users").document(uid).collection("source_consents")

    async def append(self, decision: ConsentDecision) -> None:
        try:
            await asyncio.to_thread(
                self._decisions(decision.uid).document().set,
                decision.model_dump(mode="json"),
            )
        except Exception as error:
            raise ConsentUnavailable("consent storage is unavailable") from error

    async def latest(
        self, uid: str, revision_id: str, purpose: str, provider: str
    ) -> ConsentDecision | None:
        def fetch() -> ConsentDecision | None:
            documents = (
                self._decisions(uid)
                .where("revision_id", "==", revision_id)
                .where("purpose", "==", purpose)
                .where("provider", "==", provider)
                .order_by("decided_at", direction="DESCENDING")
                .limit(1)
                .stream()
            )
            document = next(iter(documents), None)
            return ConsentDecision.model_validate(document.to_dict()) if document else None

        try:
            return await asyncio.to_thread(fetch)
        except Exception as error:
            raise ConsentUnavailable("consent storage is unavailable") from error


class FirestoreSourceMetadataStore(SourceMetadataStore):
    """Private source revision metadata scoped to the verified learner."""

    def __init__(self, db_client) -> None:
        self.db = db_client

    def _revisions(self, uid: str):
        return self.db.collection("users").document(uid).collection("source_revisions")

    async def find_revision(
        self, uid: str, canonical_url: str, content_hash: str
    ) -> SourceRevision | None:
        def fetch() -> SourceRevision | None:
            documents = (
                self._revisions(uid)
                .where("canonical_url", "==", canonical_url)
                .where("content_hash", "==", content_hash)
                .limit(1)
                .stream()
            )
            document = next(iter(documents), None)
            return SourceRevision.model_validate(document.to_dict()) if document else None

        return await asyncio.to_thread(fetch)

    async def save_revision(self, revision: SourceRevision) -> None:
        await asyncio.to_thread(
            self._revisions(revision.uid).document(revision.id).create,
            revision.model_dump(mode="json"),
        )


class FirestoreConceptStore:
    """Stores curriculum concepts, modules, and ingested lecture notes scoped under the learner path."""

    def __init__(self, db_client) -> None:
        self.db = db_client

    def _concepts(self, uid: str):
        return self.db.collection("users").document(uid).collection("concepts")

    def _modules(self, uid: str):
        return self.db.collection("users").document(uid).collection("modules")

    def _sources(self, uid: str):
        return self.db.collection("users").document(uid).collection("sources")

    async def save_concept(self, uid: str, concept: ConceptNode) -> None:
        def write():
            self._concepts(uid).document(concept.slug).set(
                concept.model_dump(mode="json")
            )

        await asyncio.to_thread(write)

    async def get_concept(self, uid: str, slug: str) -> ConceptNode | None:
        def fetch():
            doc = self._concepts(uid).document(slug).get()
            if not doc.exists:
                return None
            return ConceptNode.model_validate(doc.to_dict())

        return await asyncio.to_thread(fetch)

    async def list_concepts(self, uid: str, module: str | None = None) -> list[ConceptNode]:
        def fetch():
            query = self._concepts(uid)
            if module:
                query = query.where("module", "==", module)
            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                results.append(ConceptNode.model_validate(data))
            results.sort(key=lambda c: (c.module, c.order, c.slug))
            return results

        return await asyncio.to_thread(fetch)

    async def append_citation(self, uid: str, slug: str, citation_text: str) -> None:
        def update():
            doc_ref = self._concepts(uid).document(slug)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                citations = list(data.get("citations", []))
                if citation_text not in citations:
                    citations.append(citation_text)
                    doc_ref.update({"citations": citations})

        await asyncio.to_thread(update)

    async def save_module(self, uid: str, module: CourseModule) -> None:
        def write():
            self._modules(uid).document(module.module_id).set(
                module.model_dump(mode="json")
            )

        await asyncio.to_thread(write)

    async def list_modules(self, uid: str) -> list[CourseModule]:
        def fetch():
            docs = self._modules(uid).stream()
            modules = [CourseModule.model_validate(d.to_dict()) for d in docs]
            modules.sort(key=lambda m: m.module_id)
            return modules

        return await asyncio.to_thread(fetch)

    async def save_source(self, uid: str, source_id: str, data: dict) -> None:
        def write():
            self._sources(uid).document(source_id).set(data)

        await asyncio.to_thread(write)

    async def list_sources(self, uid: str) -> list[dict]:
        def fetch():
            docs = self._sources(uid).stream()
            sources = [d.to_dict() for d in docs]
            sources.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return sources

        return await asyncio.to_thread(fetch)

    async def get_source(self, uid: str, source_id: str) -> dict | None:
        def fetch():
            doc = self._sources(uid).document(source_id).get()
            return doc.to_dict() if doc.exists else None

        return await asyncio.to_thread(fetch)

