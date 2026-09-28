"""Configuration loading.

Config lives in `config.toml` (committed, no secrets) and `.env` (gitignored,
secrets only). Nothing in this module reaches the network or touches the DB.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config.toml"


def _load_env(path: Path) -> None:
    """Minimal .env reader. Existing environment always wins."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    root: Path

    # --- convenience accessors -------------------------------------------------
    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, path: str, default: Any = None) -> Any:
        """Dotted lookup, e.g. cfg.get('video.width', 1920)."""
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def work_dir(self) -> Path:
        return (self.root / self.get("paths.work_dir", "work")).resolve()

    @property
    def stock_dir(self) -> Path:
        return (self.root / self.get("paths.stock_dir", "stock")).resolve()

    @property
    def db_path(self) -> Path:
        return (self.root / self.get("paths.db", "work/yta.sqlite3")).resolve()

    def job_dir(self, job_id: int) -> Path:
        return self.work_dir / f"job-{job_id:04d}"


def load(path: Path | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"No config at {cfg_path}. Copy config.example.toml to config.toml."
        )
    root = cfg_path.resolve().parent
    _load_env(root / ".env")
    with cfg_path.open("rb") as fh:
        raw = tomllib.load(fh)
    return Config(raw=raw, root=root)
