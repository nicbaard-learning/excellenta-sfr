"""Application configuration via environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "postgresql://sfr:sfr@localhost:5432/sfr"

    # ── Application ───────────────────────────────────────────────────
    app_title: str = "SFR – Shared Framework Repository"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Import ────────────────────────────────────────────────────────
    default_workbook: str = "secure-controls-framework-scf-2026-1.xlsx"
    import_batch_size: int = 500


settings = Settings()
