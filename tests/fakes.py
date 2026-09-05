from typing import Optional
from app.domain.models import InteractionRecord

class FakeInteractionStore:
    def __init__(self):
        self.records: dict[tuple[str, str], InteractionRecord] = {}

    async def get_interaction(self, user_id: str, interaction_id: str) -> Optional[InteractionRecord]:
        return self.records.get((user_id, interaction_id))

    async def save_interaction(self, record: InteractionRecord) -> None:
        self.records[(record.user_id, record.interaction_id)] = record
