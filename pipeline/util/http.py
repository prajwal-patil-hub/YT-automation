"""Minimal HTTP helper with an injectable transport.

Both API clients in this project speak plain JSON over HTTPS, so they are built
on urllib rather than a dependency. The transport is injectable so every client
can be exercised offline against a fake — which matters here, because the
Telegram and Google endpoints are unreachable from some build environments.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class HTTPError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} from {url}: {body[:400]}")


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8") or "{}")


class Transport(Protocol):
    def request(self, method: str, url: str, *, data: bytes | None = None,
                headers: dict[str, str] | None = None, timeout: float = 60.0) -> Response: ...


class UrllibTransport:
    def request(self, method: str, url: str, *, data: bytes | None = None,
                headers: dict[str, str] | None = None, timeout: float = 60.0) -> Response:
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return Response(resp.status, resp.read(), dict(resp.headers))
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return Response(exc.code, body, dict(exc.headers or {}))


def post_json(transport: Transport, url: str, payload: dict[str, Any],
              *, headers: dict[str, str] | None = None, timeout: float = 60.0) -> Response:
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **(headers or {})}
    return transport.request("POST", url, data=data, headers=h, timeout=timeout)


def post_form(transport: Transport, url: str, fields: dict[str, Any],
              *, headers: dict[str, str] | None = None, timeout: float = 60.0) -> Response:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    return transport.request("POST", url, data=data, headers=h, timeout=timeout)


def encode_multipart(fields: dict[str, Any],
                     files: dict[str, Path] | None = None) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body, content_type)."""
    boundary = "----ytauto" + secrets.token_hex(16)
    out = bytearray()

    def line(text: str = "") -> None:
        out.extend(text.encode("utf-8"))
        out.extend(b"\r\n")

    for name, value in fields.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif not isinstance(value, str):
            value = json.dumps(value)
        line(f"--{boundary}")
        line(f'Content-Disposition: form-data; name="{name}"')
        line()
        line(value)

    for name, path in (files or {}).items():
        path = Path(path)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        line(f"--{boundary}")
        line(f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"')
        line(f"Content-Type: {ctype}")
        line()
        out.extend(path.read_bytes())
        out.extend(b"\r\n")

    line(f"--{boundary}--")
    return bytes(out), f"multipart/form-data; boundary={boundary}"
