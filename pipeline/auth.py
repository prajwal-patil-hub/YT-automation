"""One-time credential setup.

Getting a YouTube refresh token is otherwise a documentation exercise: register
a client, assemble a consent URL by hand, copy a code out of a browser bar,
POST it somewhere. This turns it into one command.

Everything is stdlib. The OAuth flow uses the loopback redirect that Google
documents for installed apps, with PKCE, so no secret ever travels in a URL.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .util.http import Transport, UrllibTransport, post_form
from .util.telegram import TelegramClient, TelegramError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# upload: publish videos and set thumbnails. force-ssl: upload caption tracks.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class AuthError(RuntimeError):
    pass


# --- PKCE -------------------------------------------------------------------

def make_verifier() -> str:
    """A high-entropy code verifier (RFC 7636 allows 43-128 chars)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")


def challenge_for(verifier: str) -> str:
    """S256 challenge: base64url(sha256(verifier)), unpadded."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_auth_url(client_id: str, redirect_uri: str, *, verifier: str,
                   state: str, scopes: list[str] | None = None) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes or SCOPES),
        # Both are required to be *given* a refresh token at all, and
        # prompt=consent is what makes Google re-issue one on a repeat run.
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge_for(verifier),
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


# --- loopback receiver ------------------------------------------------------

@dataclass
class _Result:
    code: str | None = None
    error: str | None = None
    state: str | None = None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _handler_factory(result: _Result, expected_state: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got_state = (query.get("state") or [None])[0]
            if got_state != expected_state:
                # A mismatched state means this redirect is not the one we
                # started, so the code it carries is not ours to use.
                result.error = "state mismatch — ignoring this redirect"
                body = "Something went wrong: unexpected state. Nothing was saved."
            elif "error" in query:
                result.error = query["error"][0]
                body = f"Authorisation failed: {result.error}. You can close this tab."
            else:
                result.code = (query.get("code") or [None])[0]
                result.state = got_state
                body = "Authorised. You can close this tab and go back to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, *args):  # silence the default stderr logging
            pass

    return Handler


def exchange_code(client_id: str, client_secret: str, code: str,
                  redirect_uri: str, verifier: str, *,
                  transport: Transport | None = None) -> dict[str, Any]:
    resp = post_form(transport or UrllibTransport(), TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    })
    if resp.status != 200:
        raise AuthError(f"Token exchange failed ({resp.status}): {resp.body[:300]!r}")
    data = resp.json()
    if "refresh_token" not in data:
        raise AuthError(
            "Google returned no refresh token. This happens when the account has "
            "already granted this client and Google reuses the earlier grant.\n"
            "  Remove it at https://myaccount.google.com/permissions and run this again."
        )
    return data


def youtube_flow(client_id: str, client_secret: str, *,
                 timeout: float = 300.0, open_browser: bool = True,
                 transport: Transport | None = None) -> dict[str, Any]:
    """Run the loopback consent flow and return the token response."""
    if not client_id or not client_secret:
        raise AuthError(
            "Need a client id and secret from a Google Cloud OAuth client of "
            "type 'Desktop app'. See docs/08."
        )

    port = free_port()
    redirect_uri = f"http://127.0.0.1:{port}"
    verifier = make_verifier()
    state = secrets.token_urlsafe(24)
    result = _Result()

    server = http.server.HTTPServer(("127.0.0.1", port), _handler_factory(result, state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = build_auth_url(client_id, redirect_uri, verifier=verifier, state=state)
    print("\nOpen this URL and grant access:\n")
    print(f"  {url}\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — a headless box has no browser, that's fine
            pass
    print(f"Waiting for the redirect on {redirect_uri} …")

    waited = 0.0
    try:
        while result.code is None and result.error is None and waited < timeout:
            threading.Event().wait(0.5)
            waited += 0.5
    finally:
        server.shutdown()
        server.server_close()

    if result.error:
        raise AuthError(result.error)
    if not result.code:
        raise AuthError(f"No redirect arrived within {timeout:.0f}s.")

    return exchange_code(client_id, client_secret, result.code,
                         redirect_uri, verifier, transport=transport)


# --- telegram ---------------------------------------------------------------

def telegram_check(token: str, *, transport: Transport | None = None) -> dict[str, Any]:
    client = TelegramClient(token, transport=transport)
    return client._call("getMe", {})


def telegram_find_user(token: str, *, transport: Transport | None = None) -> list[dict]:
    """Read pending updates to discover who has messaged the bot.

    Telegram will not tell a bot its owner's id; the id only appears once a
    person sends the bot a message. So the flow is: message the bot, then run
    this.
    """
    client = TelegramClient(token, transport=transport)
    updates = client.get_updates(timeout=0)
    seen: dict[int, dict] = {}
    for update in updates:
        msg = update.get("message") or (update.get("callback_query") or {}).get("message") or {}
        sender = (update.get("message") or {}).get("from") \
            or (update.get("callback_query") or {}).get("from") or {}
        if sender.get("id"):
            seen[int(sender["id"])] = {
                "id": int(sender["id"]),
                "username": sender.get("username"),
                "first_name": sender.get("first_name"),
                "chat_id": (msg.get("chat") or {}).get("id", sender["id"]),
            }
    return list(seen.values())


# --- .env -------------------------------------------------------------------

def write_env(values: dict[str, str], path: Path) -> list[str]:
    """Set keys in .env, preserving everything else. Returns the keys changed.

    Existing values are replaced in place rather than appended, so running the
    setup twice does not leave two of the same key with the stale one winning.
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    out: list[str] = []
    changed: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                changed.append(key)
                continue
        out.append(line)

    for key, value in remaining.items():
        out.append(f"{key}={value}")
        changed.append(key)

    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    # Secrets: owner-only.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return changed
