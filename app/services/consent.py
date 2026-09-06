from typing import Protocol

from app.models.feed import ConsentDecision


class ConsentUnavailable(Exception):
    """The durable consent ledger is unavailable."""


class ConsentStore(Protocol):
    async def append(self, decision: ConsentDecision) -> None: ...

    async def latest(
        self, uid: str, revision_id: str, purpose: str, provider: str
    ) -> ConsentDecision | None: ...


class ConsentService:
    def __init__(self, store: ConsentStore) -> None:
        self.store = store

    async def record(self, decision: ConsentDecision) -> None:
        await self.store.append(decision)

    async def has_active_grant(
        self, uid: str, revision_id: str, purpose: str, provider: str
    ) -> bool:
        decision = await self.store.latest(uid, revision_id, purpose, provider)
        return decision is not None and decision.granted
