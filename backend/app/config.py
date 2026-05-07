from pydantic import BaseModel
import os


PROVIDER_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "env_key": "QWEN_API_KEY",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "env_key": "KIMI_API_KEY",
    },
}


class Settings(BaseModel):
    storage_root: str = os.getenv("SKILL_FACTORY_STORAGE", "./data")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_api_key: str = os.getenv(
        "LLM_API_KEY",
        os.getenv(
            PROVIDER_CONFIGS.get(os.getenv("LLM_PROVIDER", "openai"), {}).get("env_key", "OPENAI_API_KEY"),
            "",
        ),
    )
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")


settings = Settings()


def get_effective_provider_config() -> dict:
    """Return resolved base_url and model for the current provider."""
    provider = settings.llm_provider.lower()
    cfg = PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["openai"])
    return {
        "base_url": settings.llm_base_url or cfg["base_url"],
        "model": settings.llm_model or cfg["default_model"],
        "api_key": settings.llm_api_key,
        "provider": provider,
    }
