"""Adds the SCF licence credit to JSON API responses (pure ASGI middleware).

- Every /api/ response gets `Link: <licence>; rel="license"` and `X-SCF-Attribution`.
- JSON object bodies also get a top-level "license" key (existing fields untouched).
  Lists are left as they are (only headers), and /api/oscal/ is skipped because its
  documents carry the licence in their own metadata and must stay schema-valid.
"""

from __future__ import annotations

import json

from app import scf_attribution

SKIP_BODY_PREFIXES = ("/api/oscal",)

# Header values should be plain ASCII.
_HEADER_TEXT = scf_attribution.ATTRIBUTION.replace("®", "(R)").replace("©", "(c)")


def license_block() -> dict:
    return {
        "name": scf_attribution.LICENCE_NAME,
        "url": scf_attribution.LICENCE_URL,
        "attribution": scf_attribution.ATTRIBUTION,
    }


class SCFLicenseMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        add_body = not path.startswith(SKIP_BODY_PREFIXES)
        state: dict = {}
        chunks: list[bytes] = []

        def _headers(start: dict, drop_length: bool) -> list:
            skip = {b"x-scf-attribution", b"link"}
            if drop_length:
                skip.add(b"content-length")
            hdrs = [(k, v) for k, v in start["headers"] if k.lower() not in skip]
            hdrs.append((b"link", f'<{scf_attribution.LICENCE_URL}>; rel="license"'.encode("latin-1")))
            hdrs.append((b"x-scf-attribution", _HEADER_TEXT.encode("ascii")))
            return hdrs

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                ctype = dict(message["headers"]).get(b"content-type", b"")
                state["buffer"] = (
                    add_body and message["status"] == 200 and ctype.startswith(b"application/json")
                )
                if state["buffer"]:
                    state["start"] = message
                    return
                message = dict(message)
                message["headers"] = _headers(message, drop_length=False)
                await send(message)
                return

            if message["type"] == "http.response.body" and state.get("buffer"):
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = b"".join(chunks)
                try:
                    data = json.loads(body)
                    if isinstance(data, dict) and "license" not in data:
                        data["license"] = license_block()
                        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                except ValueError:
                    pass
                start = dict(state["start"])
                start["headers"] = _headers(start, drop_length=True) + [
                    (b"content-length", str(len(body)).encode())
                ]
                await send(start)
                await send({"type": "http.response.body", "body": body})
                return

            await send(message)

        await self.app(scope, receive, wrapped_send)
