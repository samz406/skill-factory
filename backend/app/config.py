from pydantic import BaseModel
import os


class Settings(BaseModel):
    storage_root: str = os.getenv("SKILL_FACTORY_STORAGE", "./data")


settings = Settings()
