"""Telegram Bot API client.

Built on stdlib HTTP so the project keeps a single dependency, and with an
injectable transport so the review flow can be tested without a bot token.

Two practical limits shape this:

*  The public Bot API caps bot uploads at 50 MB. A 1080p master does not fit,
   which is why the pipeline always renders a review proxy, and why `api_base`
   exists — pointing it at a self-hosted `tdlib/telegram-bot-api` raises the
   limit to 2 GB.
*  Anyone who discovers the bot can talk to it. Every update is filtered
   against an allow-list before it is acted on; without that, a stranger holds
   a publish button for your channel.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .http import HTTPError, Transport, UrllibTransport, encode_multipart, post_json

PUBLIC_API = "https://api.telegram.org"
# The public Bot API's hard ceiling for a bot upload.
PUBLIC_UPLOAD_LIMIT = 50 * 1024 * 1024


class TelegramError(RuntimeError):
    pass


@dataclass
class Callback:
    """A button press, already checked against the allow-list."""
    callback_id: str
    user_id: int
    chat_id: int
    message_id: int
    data: str
    update_id: int


class TelegramClient:
    def __init__(self, token: str, *, api_base: str = PUBLIC_API,
                 allowed_user_ids: Iterable[int] = (),
                 transport: Transport | None = None):
        if not token:
            raise TelegramError(
                "No bot token. Set TELEGRAM_BOT_TOKEN in .env "
                "(talk to @BotFather to create one)."
            )
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.allowed = {int(u) for u in allowed_user_ids if str(u).strip()}
        self.transport = transport or UrllibTransport()

    # --- plumbing -------------------------------------------------------------
    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def _call(self, method: str, payload: dict[str, Any], *,
              files: dict[str, Path] | None = None, timeout: float = 60.0) -> Any:
        url = self._url(method)
        if files:
            body, ctype = encode_multipart(payload, files)
            resp = self.transport.request(
                "POST", url, data=body, headers={"Content-Type": ctype}, timeout=timeout
            )
        else:
            resp = post_json(self.transport, url, payload, timeout=timeout)

        try:
            parsed = resp.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise TelegramError(f"{method}: unreadable response ({resp.status})") from exc

        if not parsed.get("ok"):
            raise TelegramError(
                f"{method} failed ({resp.status}): "
                f"{parsed.get('description', resp.body[:200])}"
            )
        return parsed.get("result")

    @property
    def is_self_hosted(self) -> bool:
        return self.api_base != PUBLIC_API

    def upload_limit(self) -> int:
        """2 GB against a self-hosted server, 50 MB against the public one."""
        return 2_000 * 1024 * 1024 if self.is_self_hosted else PUBLIC_UPLOAD_LIMIT

    # --- sending --------------------------------------------------------------
    def send_message(self, chat_id: int | str, text: str, *,
                     buttons: list[list[tuple[str, str]]] | None = None,
                     parse_mode: str | None = "HTML") -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id, "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": _keyboard(buttons)}
        return self._call("sendMessage", payload)

    def send_video(self, chat_id: int | str, path: Path, *, caption: str = "",
                   buttons: list[list[tuple[str, str]]] | None = None,
                   timeout: float = 600.0) -> dict:
        path = Path(path)
        size = path.stat().st_size
        limit = self.upload_limit()
        if size > limit:
            raise TelegramError(
                f"{path.name} is {size / 1e6:.0f} MB, over the "
                f"{limit / 1e6:.0f} MB limit for this API endpoint.\n"
                "  Send the review proxy instead, or run a self-hosted "
                "tdlib/telegram-bot-api server and set TELEGRAM_API_BASE."
            )
        payload: dict[str, Any] = {
            "chat_id": chat_id, "caption": caption[:1024],
            "parse_mode": "HTML", "supports_streaming": True,
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": _keyboard(buttons)}
        return self._call("sendVideo", payload, files={"video": path}, timeout=timeout)

    def send_photo(self, chat_id: int | str, path: Path, *, caption: str = "",
                   timeout: float = 180.0) -> dict:
        return self._call(
            "sendPhoto",
            {"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
            files={"photo": Path(path)}, timeout=timeout,
        )

    def answer_callback(self, callback_id: str, text: str = "") -> Any:
        return self._call("answerCallbackQuery",
                          {"callback_query_id": callback_id, "text": text[:200]})

    def edit_message_text(self, chat_id: int | str, message_id: int, text: str) -> Any:
        return self._call("editMessageText", {
            "chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": "HTML",
        })

    # --- receiving ------------------------------------------------------------
    def get_updates(self, offset: int | None = None, *, timeout: int = 30) -> list[dict]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["callback_query", "message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 15) or []

    def callbacks(self, updates: list[dict]) -> list[Callback]:
        """Extract button presses from allowed users only.

        Updates from anyone else are dropped silently — the bot is reachable by
        anyone who finds it, and this is the only thing standing between a
        stranger and your publish button.
        """
        out: list[Callback] = []
        for update in updates:
            query = update.get("callback_query")
            if not query:
                continue
            user_id = int(query.get("from", {}).get("id", 0))
            if self.allowed and user_id not in self.allowed:
                continue
            message = query.get("message") or {}
            out.append(Callback(
                callback_id=str(query.get("id", "")),
                user_id=user_id,
                chat_id=int(message.get("chat", {}).get("id", 0)),
                message_id=int(message.get("message_id", 0)),
                data=str(query.get("data", "")),
                update_id=int(update.get("update_id", 0)),
            ))
        return out


def _keyboard(rows: list[list[tuple[str, str]]]) -> list[list[dict]]:
    return [[{"text": label, "callback_data": data} for label, data in row]
            for row in rows]


def encode_action(job_id: int, action: str) -> str:
    """Callback payloads are capped at 64 bytes, so keep them terse."""
    return f"j{job_id}:{action}"


def decode_action(data: str) -> tuple[int, str] | None:
    if not data.startswith("j") or ":" not in data:
        return None
    head, _, action = data.partition(":")
    try:
        return int(head[1:]), action
    except ValueError:
        return None
