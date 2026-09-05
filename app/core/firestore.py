from typing import Protocol, Optional
from datetime import datetime
from app.domain.models import InteractionRecord

class InteractionStore(Protocol):
    async def get_interaction(self, user_id: str, interaction_id: str) -> Optional[InteractionRecord]:
        ...
        
    async def save_interaction(self, record: InteractionRecord) -> None:
        ...

class FirestoreInteractionStore:
    def __init__(self, db_client):
        self.db = db_client
        
    async def get_interaction(self, user_id: str, interaction_id: str) -> Optional[InteractionRecord]:
        doc_ref = self.db.collection("users").document(user_id).collection("interactions").document(interaction_id)
        doc = doc_ref.get()
        if doc.exists:
            return InteractionRecord(**doc.to_dict())
        return None
        
    async def save_interaction(self, record: InteractionRecord) -> None:
        doc_ref = self.db.collection("users").document(record.user_id).collection("interactions").document(record.interaction_id)
        doc_ref.set(record.model_dump(mode="json"))
