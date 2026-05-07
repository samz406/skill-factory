import json
from pathlib import Path
from uuid import uuid4
from .config import settings
from .models import Draft


class DraftStore:
    def __init__(self):
        self.root = Path(settings.storage_root)
        self.drafts = self.root / "skill_drafts"
        self.attachments = self.root / "attachments"
        self.drafts.mkdir(parents=True, exist_ok=True)
        self.attachments.mkdir(parents=True, exist_ok=True)

    def create(self) -> Draft:
        draft = Draft(conversation_id=str(uuid4()))
        self.save(draft)
        return draft

    def get(self, conversation_id: str) -> Draft:
        path = self.drafts / f"{conversation_id}.json"
        if not path.exists():
            return self.create()
        return Draft.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, draft: Draft) -> None:
        path = self.drafts / f"{draft.conversation_id}.json"
        path.write_text(json.dumps(draft.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


store = DraftStore()
