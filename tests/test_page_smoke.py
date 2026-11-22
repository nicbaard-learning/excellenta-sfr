"""Smoke test: every HTML page renders and the MCP mount answers.

Guards the starlette 1.x upgrade (TemplateResponse(request, name, ctx),
Mount/CORSMiddleware/BaseHTTPMiddleware, mcp.sse_app()). Uses the
database from .env, like the other page tests.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import _make_token
from app.database import SessionLocal
from app.main import app
from app.models.framework import Framework

client = TestClient(app)


@pytest.fixture(scope="module")
def popia():
    s = SessionLocal()
    try:
        fw = s.query(Framework).filter(Framework.code == "EMEA-ZA").first()
        assert fw is not None, "EMEA-ZA framework missing"
        return fw.id, fw.name
    finally:
        s.close()


@pytest.mark.parametrize("path", [
    "/", "/evidence", "/translate", "/maturity", "/roadmap",
    "/risk-intelligence", "/about", "/frameworks", "/recommend",
    "/compare", "/controls/GOV-01", "/health", "/static/css/sfr.css",
])
def test_page_renders(path):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])


def test_framework_and_compare_and_print_pages(popia):
    fw_id, fw_name = popia
    for path, params in [
        (f"/frameworks/{fw_id}", None),
        ("/compare", {"fw1": fw_id, "fw2": fw_id}),
        ("/recommend", {"jurisdiction": "ZA"}),
        ("/api/roadmap/print", {"framework_name": fw_name}),
    ]:
        r = client.get(path, params=params)
        assert r.status_code == 200, (path, r.status_code, r.text[:300])
        assert "<html" in r.text.lower()


def test_static_rejects_path_traversal():
    r = client.get("/static/..%2f..%2fmain.py")
    assert r.status_code == 404


# mcp's DNS-rebinding check only allows the hosts in settings (not "testserver").
HOST = {"Host": "localhost"}


@pytest.mark.parametrize("path", ["/mcp/sse", "/mcp/sse/", "/mcp/messages/",
                                  "/mcp/messages/?session_id=x", "/mcp/anything"])
@pytest.mark.parametrize("auth", [None, "Bearer not-a-token", "Basic abc"])
def test_mcp_requires_valid_token(path, auth):
    headers = dict(HOST)
    if auth:
        headers["Authorization"] = auth
    method = client.post if "messages" in path else client.get
    r = method(path, headers=headers)
    assert r.status_code == 401, (path, auth, r.status_code, r.text[:200])


def test_mcp_messages_reach_mcp_app_with_token():
    # A valid token passes auth; mcp then rejects the missing session id
    # (400), which shows the Starlette Mount + sse_app() still route.
    token = _make_token(sub="smoke-test")
    r = client.post("/mcp/messages/", json={},
                    headers={**HOST, "Authorization": f"Bearer {token}"})
    assert r.status_code == 400, (r.status_code, r.text[:300])
