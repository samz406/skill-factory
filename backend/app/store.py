from pathlib import Path
from .config import settings
from .models import Draft
from .database import init_db, db_create, db_get, db_save, db_list, db_delete


class DraftStore:
    def __init__(self):
        self.root = Path(settings.storage_root)
        self.attachments = self.root / "attachments"
        self.attachments.mkdir(parents=True, exist_ok=True)
        init_db()

    def create(self) -> Draft:
        return db_create()

    def get(self, conversation_id: str) -> Draft:
        draft = db_get(conversation_id)
        if draft is None:
            return self.create()
        return draft

    def save(self, draft: Draft) -> None:
        db_save(draft)

    def list(self):
        return db_list()

    def delete(self, conversation_id: str) -> bool:
        return db_delete(conversation_id)


store = DraftStore()
