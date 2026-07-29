"""Shared helpers — paths, config loading, logging, JSON persistence."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

BRAND_YAML = CONFIG_DIR / "brand.yaml"
SEO_YAML = CONFIG_DIR / "seo_targets.yaml"
SCHRIJF_INSTRUCTIE_MD = CONFIG_DIR / "schrijf_instructie.md"
PRODUCTS_JSON = DATA_DIR / "products.json"
KEYWORDS_JSON = DATA_DIR / "keyword_bank.json"
PUBLISHED_JSON = DATA_DIR / "published.json"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

console = Console()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = RichHandler(console=console, show_time=True, show_path=False, markup=True)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Env + config loading
# ---------------------------------------------------------------------------


def load_env() -> None:
    """Load .env once. Safe to call multiple times."""
    load_dotenv(ROOT / ".env", override=False)


def env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    load_env()
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


@lru_cache(maxsize=1)
def load_brand() -> dict[str, Any]:
    with BRAND_YAML.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schrijf_instructie() -> str:
    if SCHRIJF_INSTRUCTIE_MD.exists():
        return SCHRIJF_INSTRUCTIE_MD.read_text(encoding="utf-8")
    return ""


@lru_cache(maxsize=1)
def load_seo_targets() -> dict[str, Any]:
    with SEO_YAML.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_products() -> list[dict[str, Any]]:
    with PRODUCTS_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("products", [])


def get_product(handle: str) -> dict[str, Any] | None:
    for p in load_products():
        if p.get("handle") == handle:
            return p
    return None


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunContext:
    """Lightweight context passed between pipeline steps."""

    dry_run: bool
    min_seo_score: int
    model: str
    count: int
    started_at: str

    @classmethod
    def from_env(cls, *, dry_run: bool, count: int) -> "RunContext":
        return cls(
            dry_run=dry_run,
            min_seo_score=int(env("AGENT_MIN_SEO_SCORE", "85") or 85),
            model=env("CLAUDE_MODEL", "claude-sonnet-4-5") or "claude-sonnet-4-5",
            count=count,
            started_at=now_iso(),
        )
