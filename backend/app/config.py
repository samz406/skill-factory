from pydantic import BaseModel
import json
import os
from pathlib import Path


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

_CONFIG_FILE = Path(os.getenv("SKILL_FACTORY_STORAGE", "./data")) / "llm_config.json"


def _load_config_file() -> dict:
    """Load LLM config from file, return empty dict if not found."""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


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


def _init_settings() -> Settings:
    """Create Settings, overlaying saved file config on top of env vars."""
    s = Settings()
    saved = _load_config_file()
    if saved.get("llm_provider"):
        s.llm_provider = saved["llm_provider"]
    if saved.get("llm_api_key"):
        s.llm_api_key = saved["llm_api_key"]
    if saved.get("llm_model"):
        s.llm_model = saved["llm_model"]
    if saved.get("llm_base_url"):
        s.llm_base_url = saved["llm_base_url"]
    return s


settings = _init_settings()


def save_llm_config(provider: str, api_key: str, model: str, base_url: str) -> None:
    """Persist LLM config to file (mode 0600) and update the running settings."""
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "llm_provider": provider,
        "llm_api_key": api_key,
        "llm_model": model,
        "llm_base_url": base_url,
    }
    _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _CONFIG_FILE.chmod(0o600)
    settings.llm_provider = provider
    settings.llm_api_key = api_key
    settings.llm_model = model
    settings.llm_base_url = base_url


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
