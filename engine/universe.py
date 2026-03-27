"""
engine/universe.py — Dynamic universe manager
===============================================
All tickers added by Trade Ideas, predict_tomorrow, or manual injection live
here in ``data/universe.json``.  Tickers expire automatically after their TTL
so the list never balloons.

Schema (data/universe.json)
----------------------------
{
  "version": 1,
  "updated": "YYYY-MM-DD",
  "tickers": {
    "KOD":  {"tier": 1, "added": "2026-03-26"},
    "MDGL": {"tier": 2, "added": "2026-03-26"},
    ...
  }
}

TTL rules (configurable via config.py or env):
  Tier 1 (momentum)   → 14 days  (fast-movers go stale quickly)
  Tier 2 (established)→ 30 days
  Tier 3 (following)  → 7 days   (daily watchlist / prediction picks)

Core tickers hardcoded in config.py are NOT managed here and never expire.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT   = Path(__file__).parent.parent
DATA_DIR     = _REPO_ROOT / "data"
UNIVERSE_FILE = DATA_DIR / "universe.json"

# ── TTL per tier (days) ───────────────────────────────────────────────────────
TIER_TTL: dict[int, int] = {
    1: int(os.getenv("UNIVERSE_TTL_TIER1", "14")),
    2: int(os.getenv("UNIVERSE_TTL_TIER2", "30")),
    3: int(os.getenv("UNIVERSE_TTL_TIER3", "7")),
}

_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_raw() -> dict:
    """Read universe.json from disk.  Returns empty schema on missing/corrupt file."""
    if not UNIVERSE_FILE.exists():
        return {"version": 1, "updated": str(date.today()), "tickers": {}}
    try:
        return json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated": str(date.today()), "tickers": {}}


def _save_raw(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["updated"] = str(date.today())
    UNIVERSE_FILE.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _is_expired(entry: dict) -> bool:
    tier = int(entry.get("tier", 1))
    ttl  = TIER_TTL.get(tier, 14)
    try:
        added = date.fromisoformat(entry["added"])
    except (KeyError, ValueError):
        return False  # unknown date → keep
    return (date.today() - added).days > ttl


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def add_tickers(
    symbols: list[str],
    tier: Literal[1, 2, 3] = 1,
    today: str | None = None,
) -> int:
    """Add or refresh tickers.  Returns the number of *new* tickers inserted."""
    added_date = today or str(date.today())
    with _lock:
        data = _load_raw()
        tickers = data.setdefault("tickers", {})
        fresh = 0
        for sym in symbols:
            sym = sym.strip().upper()
            if not sym:
                continue
            if sym not in tickers:
                fresh += 1
            # Refresh date whether new or existing — keeps active ones alive
            tickers[sym] = {"tier": tier, "added": added_date}
        _save_raw(data)
    return fresh


def get_tier(tier: int) -> list[str]:
    """Return all non-expired tickers for a given tier, sorted alphabetically."""
    data = _load_raw()
    today = date.today()
    out = []
    for sym, entry in data.get("tickers", {}).items():
        if int(entry.get("tier", 1)) == tier and not _is_expired(entry):
            out.append(sym)
    return sorted(out)


def prune(dry_run: bool = False) -> list[str]:
    """Remove expired tickers.  Returns the list of removed symbols."""
    with _lock:
        data  = _load_raw()
        tickers = data.get("tickers", {})
        expired = [sym for sym, entry in tickers.items() if _is_expired(entry)]
        if not dry_run:
            for sym in expired:
                del tickers[sym]
            _save_raw(data)
    return sorted(expired)


def stats() -> dict:
    """Return a summary dict for logging/display."""
    data    = _load_raw()
    tickers = data.get("tickers", {})
    alive   = {s: e for s, e in tickers.items() if not _is_expired(e)}
    expired = {s: e for s, e in tickers.items() if _is_expired(e)}
    by_tier: dict[int, int] = {}
    for e in alive.values():
        t = int(e.get("tier", 1))
        by_tier[t] = by_tier.get(t, 0) + 1
    return {
        "total_alive":   len(alive),
        "total_expired": len(expired),
        "by_tier":       by_tier,
        "file":          str(UNIVERSE_FILE),
    }
