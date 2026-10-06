"""Configuration for the extraction worker service."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Firecrawl configuration
    firecrawl_api_key: str = ""
    firecrawl_api_url: str = "https://api.firecrawl.dev"

    # Service configuration
    service_name: str = "regtrack-extraction-worker"
    log_level: str = "INFO"

    # Request defaults
    default_timeout: int = 60
    max_content_length: int = 10_000_000  # 10MB

    # BeautifulSoup defaults
    bs4_parser: str = "lxml"

    model_config = {"env_prefix": "EXTRACT_", "env_file": ".env"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
