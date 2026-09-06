import asyncio
from collections.abc import Callable
from typing import Protocol

from google.cloud.firestore_v1 import transactional

from app.domain.models import ConnectionProposal, ReviewResult


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
