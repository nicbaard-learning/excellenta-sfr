"""MCP (Model Context Protocol) server for the SFR – AI-natural-language access layer."""


def __getattr__(name):
    """Lazy-import submodules to avoid RuntimeWarning from eager DB setup at import time."""
    if name == "mcp":
        from app.mcp.server import mcp  # noqa: PLC0415
        return mcp
    if name == "create_sse_app":
        from app.mcp.server import create_sse_app  # noqa: PLC0415
        return create_sse_app
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["mcp", "create_sse_app"]
