"""Configuration for the ai service.

All values are read lazily from environment variables so tests can monkeypatch
them. A best-effort `.env` loader runs once at import time.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent.parent  # services/ai


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - dotenv is optional
        return
    for candidate in (_SERVICE_DIR / ".env", _SERVICE_DIR.parent.parent / ".env"):
        try:
            if candidate.is_file():
                load_dotenv(candidate, override=False)
        except Exception:  # pragma: no cover - never fail on dotenv
            pass


_load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def repo_root() -> Path:
    """Project root (D:\\AI_Hack locally, overridable in containers)."""
    override = env("REPO_ROOT")
    if override:
        return Path(override)
    root = _SERVICE_DIR.parent.parent
    if root.name.lower() == "services" or (root / "backend").exists() or (root / ".agents").exists():
        return root
    return Path.cwd()


def storage_root() -> Path:
    override = env("STORAGE_ROOT")
    if override:
        return Path(override)
    return repo_root() / "storage"


def processed_dir(regulation_id: int) -> Path:
    return storage_root() / "processed" / str(regulation_id)


def analysis_dir(regulation_id: int) -> Path:
    return storage_root() / "analysis" / str(regulation_id)


def chroma_dir() -> Path:
    override = env("CHROMA_DIR")
    if override:
        return Path(override)
    return storage_root() / "chroma"


def api_base() -> str:
    return (env("API_BASE", "http://localhost:8080") or "").rstrip("/")


def admin_email() -> str:
    return env("ADMIN_EMAIL", "admin@regtrack.local") or "admin@regtrack.local"


def admin_password() -> str:
    return env("ADMIN_PASSWORD", "Admin@12345") or "Admin@12345"


def llm_timeout() -> float:
    return float(env("AI_TIMEOUT", "60") or "60")


def llm_retries() -> int:
    return env_int("AI_RETRIES", 2)


def force_stub() -> bool:
    return env_bool("AI_FORCE_STUB", False)


@lru_cache(maxsize=1)
def llm_provider_config() -> dict:
    """Resolve provider credentials.

    Priority: OPENAI_API_KEY -> GEMINI_API_KEY (Gemini OpenAI-compat endpoint)
    -> LLM_API_KEY (generic OpenAI-compatible endpoint via LLM_BASE_URL).
    Returns an empty dict when no key is configured (stub mode).
    """
    openai_key = env("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "openai",
            "api_key": openai_key,
            "base_url": env("OPENAI_BASE_URL"),  # None => OpenAI default
            "model": env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        }

    gemini_key = env("GEMINI_API_KEY")
    if gemini_key:
        return {
            "provider": "gemini",
            "api_key": gemini_key,
            "base_url": env(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            "model": env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        }

    generic_key = env("LLM_API_KEY")
    if generic_key:
        return {
            "provider": "openai-compatible",
            "api_key": generic_key,
            "base_url": env("LLM_BASE_URL"),
            "model": env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        }

    return {}


def clear_provider_cache() -> None:
    """Testing hook: forget cached provider resolution."""
    llm_provider_config.cache_clear()
