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

    # ── MCP ────────────────────────────────────────────────────────────
    mcp_api_key: str = ""

    # OAuth 2.0 settings for Claude.ai connector integration.
    # Set these via environment variables for production.
    mcp_oauth_client_id: str = "sfr-mcp"
    mcp_oauth_client_secret: str = ""
    mcp_jwt_secret: str = ""
    mcp_oauth_base_url: str = "https://excellenta-sfr.onrender.com"

    # Allowed Host header values for the MCP transport (DNS rebinding protection).
    # Comma-separated list; set via the MCP_ALLOWED_HOSTS env var.
    # Supports exact hostnames and port-wildcard patterns like "localhost:*".
    mcp_allowed_hosts: str = (
        "127.0.0.1,127.0.0.1:*,localhost,localhost:*,"
        "[::1],[::1]:*,excellenta-sfr.onrender.com"
    )

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        """Parse the comma-separated MCP_ALLOWED_HOSTS into a list."""
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]

    # Allowed Origin header values for the MCP transport (DNS rebinding protection).
    # Comma-separated list; set via the MCP_ALLOWED_ORIGINS env var.
    mcp_allowed_origins: str = (
        "http://127.0.0.1,http://127.0.0.1:*,http://localhost,http://localhost:*,"
        "http://[::1],http://[::1]:*,https://excellenta-sfr.onrender.com"
    )

    @property
    def mcp_allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated MCP_ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.mcp_allowed_origins.split(",") if o.strip()]


settings = Settings()
