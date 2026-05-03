from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "knowledge-rss-api"
    app_env: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = Field(alias="DATABASE_URL")
    public_site_url: str = "http://127.0.0.1:4321"
    backend_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:4321", "http://localhost:4321"]
    )

    supabase_url: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str | None = None
    admin_api_token: str | None = None

    ai_api_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "gpt-4.1-mini"

    rss_scheduler_enabled: bool = True
    rss_scheduler_interval_minutes: int = 15
    rss_feed_timeout_seconds: float = 35.0
    rss_cache_ttl_seconds: int = 180
    rss_max_parallel_fetches: int = 6
    rss_max_parallel_summaries: int = 4
    rss_summary_max_chars: int = 6000
    rss_summary_recovery_batch_size: int = 24
    rss_summary_failed_retry_after_minutes: int = 60
    rss_summary_processing_timeout_minutes: int = 20
    rss_fetch_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    )
    rss_fetch_accept_language: str = "en-US,en;q=0.9,zh-CN;q=0.8"
    rss_fetch_proxy_url: str | None = None
    rss_fetch_proxy_token: str | None = None
    rss_fetch_proxy_hosts: list[str] = Field(default_factory=list)

    db_pool_min_size: int = 1
    db_pool_max_size: int = 8

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("rss_fetch_proxy_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: str | list[str]) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [host.strip().lower() for host in value.split(",") if host.strip()]
        return [host.strip().lower() for host in value if isinstance(host, str) and host.strip()]

    @property
    def resolved_supabase_jwks_url(self) -> str | None:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    @property
    def resolved_supabase_issuer(self) -> str | None:
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1"
        return None

    @property
    def rss_fetch_proxy_enabled(self) -> bool:
        return bool(self.rss_fetch_proxy_url and self.rss_fetch_proxy_token)


settings = Settings()
