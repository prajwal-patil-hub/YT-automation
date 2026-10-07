"""SQLite job store.

Three things live here that the pipeline genuinely depends on:

1. Stage state, so a crashed or interrupted run resumes instead of restarting.
2. An asset manifest with provenance, which is what lets the publish stage
   *derive* the altered-or-synthetic disclosure flag instead of relying on
   someone remembering to set it.
3. Asset content hashes, so we can warn when the same clip shows up in
   consecutive videos — the reuse that template-detection looks for.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL DEFAULT 'default',
    topic           TEXT NOT NULL,
    title           TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    meta            TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS stages (
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL,          -- pending | running | done | failed
    started_at      REAL,
    finished_at     REAL,
    error           TEXT,
    PRIMARY KEY (job_id, name)
);

CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    beat_index      INTEGER,
    stage           TEXT NOT NULL DEFAULT 'unknown',  -- stage that produced it
    kind            TEXT NOT NULL,          -- card | chart | stock | colour | audio
    path            TEXT NOT NULL,
    sha256          TEXT,
    provider        TEXT NOT NULL,
    source_url      TEXT,
    license         TEXT,
    generated       INTEGER NOT NULL DEFAULT 0,   -- produced by a generative model
    photorealistic  INTEGER NOT NULL DEFAULT 0,   -- depicts real-looking people/places
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    checkpoint      TEXT NOT NULL,          -- script | video
    state           TEXT NOT NULL,          -- pending | approved | rejected | redo
    decision        TEXT,
    message_id      INTEGER,
    notes           TEXT,
    decided_at      REAL,
    PRIMARY KEY (job_id, checkpoint)
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER,
    at              REAL NOT NULL,
    level           TEXT NOT NULL,
    stage           TEXT,
    message         TEXT NOT NULL
);
"""

# Indexes are applied *after* migrations: an index on a column that an older
# database has not got yet would abort the whole schema script, and the
# migration that adds the column would then never run.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_assets_sha ON assets(sha256);
CREATE INDEX IF NOT EXISTS idx_assets_job ON assets(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_channel ON jobs(channel);
"""


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.executescript(INDEXES)
        self.conn.commit()

    def _migrate(self) -> None:
        """Additive migrations for databases created by an earlier version."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        if "channel" not in cols:
            self.conn.execute(
                "ALTER TABLE jobs ADD COLUMN channel TEXT NOT NULL DEFAULT 'default'"
            )
        acols = {r["name"] for r in self.conn.execute("PRAGMA table_info(assets)")}
        if "stage" not in acols:
            self.conn.execute(
                "ALTER TABLE assets ADD COLUMN stage TEXT NOT NULL DEFAULT 'unknown'"
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- jobs -----------------------------------------------------------------
    def create_job(self, topic: str, meta: dict[str, Any] | None = None,
                   *, channel: str = "default") -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO jobs (channel, topic, status, created_at, updated_at, meta)"
            " VALUES (?, ?, 'new', ?, ?, ?)",
            (channel, topic, now, now, json.dumps(meta or {})),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_job(self, job_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()

    def list_jobs(self, limit: int = 25, *, channel: str | None = None) -> list[sqlite3.Row]:
        if channel:
            return list(self.conn.execute(
                "SELECT * FROM jobs WHERE channel = ? ORDER BY id DESC LIMIT ?",
                (channel, limit)))
        return list(self.conn.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)))

    def channel_counts(self) -> dict[str, int]:
        return {r["channel"]: r["n"] for r in self.conn.execute(
            "SELECT channel, COUNT(*) AS n FROM jobs GROUP BY channel ORDER BY channel")}

    def update_job(self, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        if "meta" in fields and isinstance(fields["meta"], dict):
            fields["meta"] = json.dumps(fields["meta"])
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id)
        )
        self.conn.commit()

    def job_meta(self, job_id: int) -> dict[str, Any]:
        row = self.get_job(job_id)
        if not row:
            return {}
        try:
            return json.loads(row["meta"])
        except (ValueError, TypeError):
            return {}

    def merge_meta(self, job_id: int, **values: Any) -> dict[str, Any]:
        meta = self.job_meta(job_id)
        meta.update(values)
        self.update_job(job_id, meta=meta)
        return meta

    # --- stages ---------------------------------------------------------------
    def stage_status(self, job_id: int, name: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM stages WHERE job_id = ? AND name = ?", (job_id, name)
        ).fetchone()
        return row["status"] if row else None

    def stage_begin(self, job_id: int, name: str) -> None:
        self.conn.execute(
            "INSERT INTO stages (job_id, name, status, started_at) VALUES (?, ?, 'running', ?)"
            " ON CONFLICT(job_id, name) DO UPDATE SET"
            " status='running', started_at=excluded.started_at, error=NULL, finished_at=NULL",
            (job_id, name, time.time()),
        )
        self.conn.commit()

    def stage_done(self, job_id: int, name: str) -> None:
        self.conn.execute(
            "UPDATE stages SET status='done', finished_at=? WHERE job_id=? AND name=?",
            (time.time(), job_id, name),
        )
        self.conn.commit()

    def stage_failed(self, job_id: int, name: str, error: str) -> None:
        self.conn.execute(
            "UPDATE stages SET status='failed', finished_at=?, error=? WHERE job_id=? AND name=?",
            (time.time(), error[:4000], job_id, name),
        )
        self.conn.commit()

    def stages_for(self, job_id: int) -> dict[str, sqlite3.Row]:
        rows = self.conn.execute("SELECT * FROM stages WHERE job_id = ?", (job_id,))
        return {r["name"]: r for r in rows}

    def reset_stages(self, job_id: int, names: Iterable[str]) -> None:
        for name in names:
            self.conn.execute(
                "DELETE FROM stages WHERE job_id=? AND name=?", (job_id, name)
            )
        self.conn.commit()

    # --- assets ---------------------------------------------------------------
    def add_asset(
        self,
        job_id: int,
        kind: str,
        path: str | Path,
        provider: str,
        *,
        stage: str = "unknown",
        beat_index: int | None = None,
        source_url: str | None = None,
        license: str | None = None,
        generated: bool = False,
        photorealistic: bool = False,
    ) -> int:
        path = Path(path)
        digest = sha256_file(path) if path.exists() else None
        cur = self.conn.execute(
            "INSERT INTO assets (job_id, stage, beat_index, kind, path, sha256, provider,"
            " source_url, license, generated, photorealistic, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id, stage, beat_index, kind, str(path), digest, provider,
                source_url, license, int(generated), int(photorealistic), time.time(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def clear_stage_assets(self, job_id: int, stage: str) -> int:
        """Drop a stage's prior assets before it re-runs.

        Without this, re-running a stage appends rather than replaces, and a
        stale generated asset would keep `requires_disclosure` true after the
        visual that caused it has been swapped out.
        """
        cur = self.conn.execute(
            "DELETE FROM assets WHERE job_id = ? AND stage = ?", (job_id, stage)
        )
        self.conn.commit()
        return cur.rowcount

    def assets_for(self, job_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM assets WHERE job_id = ? ORDER BY beat_index, id", (job_id,)
            )
        )

    def requires_disclosure(self, job_id: int) -> bool:
        """Derive YouTube's altered-or-synthetic flag from what actually went in.

        This is a query, not a judgement call — which is the whole point of
        recording provenance per asset.
        """
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM assets"
            " WHERE job_id = ? AND generated = 1 AND photorealistic = 1",
            (job_id,),
        ).fetchone()
        return bool(row["n"])

    def reused_assets(self, job_id: int) -> list[sqlite3.Row]:
        """Assets in this job whose bytes already appeared in an earlier job."""
        return list(
            self.conn.execute(
                "SELECT a.beat_index, a.path, a.sha256, a.provider,"
                "       (SELECT GROUP_CONCAT(DISTINCT b.job_id) FROM assets b"
                "         WHERE b.sha256 = a.sha256 AND b.job_id < a.job_id) AS seen_in,"
                "       (SELECT GROUP_CONCAT(DISTINCT j.channel) FROM assets b"
                "         JOIN jobs j ON j.id = b.job_id"
                "         WHERE b.sha256 = a.sha256 AND b.job_id < a.job_id) AS seen_channels"
                "  FROM assets a"
                " WHERE a.job_id = ? AND a.sha256 IS NOT NULL"
                "   AND EXISTS (SELECT 1 FROM assets b"
                "                WHERE b.sha256 = a.sha256 AND b.job_id < a.job_id)",
                (job_id,),
            )
        )

    # --- approvals ------------------------------------------------------------
    def set_approval(self, job_id: int, checkpoint: str, state: str, *,
                     decision: str | None = None, message_id: int | None = None,
                     notes: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO approvals (job_id, checkpoint, state, decision, message_id,"
            " notes, decided_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(job_id, checkpoint) DO UPDATE SET"
            " state=excluded.state, decision=excluded.decision,"
            " message_id=COALESCE(excluded.message_id, approvals.message_id),"
            " notes=excluded.notes, decided_at=excluded.decided_at",
            (job_id, checkpoint, state, decision, message_id, notes,
             time.time() if state != "pending" else None),
        )
        self.conn.commit()

    def get_approval(self, job_id: int, checkpoint: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM approvals WHERE job_id = ? AND checkpoint = ?",
            (job_id, checkpoint),
        ).fetchone()

    def pending_approvals(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT a.*, j.channel, j.title, j.topic FROM approvals a"
            " JOIN jobs j ON j.id = a.job_id"
            " WHERE a.state = 'pending' ORDER BY a.job_id"))

    # --- events ---------------------------------------------------------------
    def log(self, job_id: int | None, level: str, message: str, stage: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO events (job_id, at, level, stage, message) VALUES (?,?,?,?,?)",
            (job_id, time.time(), level, stage, message),
        )
        self.conn.commit()

    def events_for(self, job_id: int, limit: int = 100) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM events WHERE job_id = ? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            )
        )
