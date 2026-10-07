"""YouTube Data API v3 client.

Stdlib HTTP with an injectable transport, for the same reasons as the Telegram
client: one dependency for the whole project, and a flow that can be tested
without credentials.

Only the refresh-token grant is implemented. It needs no signing, so this
avoids the `cryptography` stack entirely — which matters because the official
client library's dependency chain is fragile on some platforms.
"""
from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http import HTTPError, Transport, UrllibTransport, post_form

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CAPTIONS_URL = "https://www.googleapis.com/upload/youtube/v3/captions"

# Resumable chunks must be a multiple of 256 KiB. 8 MiB keeps memory flat on a
# long upload without making the request count silly.
CHUNK = 8 * 256 * 1024


class YouTubeError(RuntimeError):
    pass


@dataclass
class UploadResult:
    video_id: str
    url: str
    privacy_status: str
    raw: dict


class YouTubeClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 *, transport: Transport | None = None):
        missing = [n for n, v in (("client id", client_id),
                                  ("client secret", client_secret),
                                  ("refresh token", refresh_token)) if not v]
        if missing:
            raise YouTubeError(
                f"Missing YouTube {', '.join(missing)}. See docs/08 for the one-time "
                "OAuth setup, and put the values in .env."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.transport = transport or UrllibTransport()
        self._access_token: str | None = None

    # --- auth -----------------------------------------------------------------
    def access_token(self, *, force: bool = False) -> str:
        if self._access_token and not force:
            return self._access_token
        resp = post_form(self.transport, TOKEN_URL, {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        })
        if resp.status != 200:
            raise YouTubeError(
                f"Token refresh failed ({resp.status}): {resp.body[:300]!r}\n"
                "  A refresh token expires after 7 days while the OAuth consent "
                "screen is still in Testing — publish it."
            )
        token = resp.json().get("access_token")
        if not token:
            raise YouTubeError("Token refresh returned no access_token")
        self._access_token = token
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token()}"}

    # --- upload ---------------------------------------------------------------
    def upload_video(self, path: Path, body: dict[str, Any], *,
                     progress: Any = None) -> UploadResult:
        path = Path(path)
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"

        start = self.transport.request(
            "POST",
            f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            data=json.dumps(body).encode("utf-8"),
            headers={
                **self._auth_headers(),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": ctype,
            },
        )
        if start.status not in (200, 201):
            raise YouTubeError(
                f"Could not start the upload ({start.status}): {start.body[:400]!r}"
            )
        session = start.headers.get("Location") or start.headers.get("location")
        if not session:
            raise YouTubeError("Upload started but returned no session URI")

        sent = 0
        with path.open("rb") as fh:
            while sent < size:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                last = sent + len(chunk) - 1
                resp = self.transport.request(
                    "PUT", session, data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {sent}-{last}/{size}",
                        "Content-Type": ctype,
                    },
                    timeout=600.0,
                )
                # 308 means "keep going"; 200/201 means the upload finished.
                if resp.status in (200, 201):
                    data = resp.json()
                    return UploadResult(
                        video_id=data.get("id", ""),
                        url=f"https://www.youtube.com/watch?v={data.get('id', '')}",
                        privacy_status=(data.get("status") or {}).get("privacyStatus", ""),
                        raw=data,
                    )
                if resp.status != 308:
                    raise YouTubeError(
                        f"Upload failed at byte {sent} ({resp.status}): {resp.body[:300]!r}"
                    )
                sent = last + 1
                if progress:
                    progress(sent, size)

        raise YouTubeError("Upload finished sending but YouTube returned no video")

    def set_thumbnail(self, video_id: str, path: Path) -> None:
        path = Path(path)
        ctype = mimetypes.guess_type(path.name)[0] or "image/png"
        resp = self.transport.request(
            "POST", f"{THUMBNAIL_URL}?videoId={video_id}",
            data=path.read_bytes(),
            headers={**self._auth_headers(), "Content-Type": ctype},
            timeout=180.0,
        )
        if resp.status not in (200, 201):
            raise YouTubeError(f"Thumbnail rejected ({resp.status}): {resp.body[:300]!r}")

    def upload_caption(self, video_id: str, path: Path, *, language: str = "en",
                       name: str = "") -> None:
        meta = {"snippet": {"videoId": video_id, "language": language,
                            "name": name, "isDraft": False}}
        from .http import encode_multipart
        body, ctype = encode_multipart({"": json.dumps(meta)}, {"file": Path(path)})
        resp = self.transport.request(
            "POST", f"{CAPTIONS_URL}?part=snippet",
            data=body, headers={**self._auth_headers(), "Content-Type": ctype},
            timeout=180.0,
        )
        if resp.status not in (200, 201):
            raise YouTubeError(f"Caption rejected ({resp.status}): {resp.body[:300]!r}")


def build_video_body(meta: dict[str, Any], *, privacy: str | None = None,
                     publish_at: str | None = None) -> dict[str, Any]:
    """Turn the packaging payload into a videos.insert resource.

    `status.containsSyntheticMedia` is the API's altered-or-synthetic
    disclosure. It is derived from the asset manifest rather than remembered,
    so it cannot drift from what actually went into the video.
    """
    status: dict[str, Any] = {
        "privacyStatus": privacy or meta.get("privacy_status", "private"),
        "selfDeclaredMadeForKids": bool(meta.get("self_declared_made_for_kids", False)),
        "containsSyntheticMedia": bool(meta.get("altered_or_synthetic_content", False)),
    }
    if publish_at:
        # A scheduled video must be uploaded private; YouTube flips it at the time.
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    return {
        "snippet": {
            "title": meta.get("title", "")[:100],
            "description": meta.get("description", "")[:5000],
            "tags": meta.get("tags", []),
            "categoryId": str(meta.get("category_id", "27")),
        },
        "status": status,
    }
