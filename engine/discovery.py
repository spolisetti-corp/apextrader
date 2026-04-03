"""
ApexTrader — Discovery
Manages live trending-stock scans and Trade Ideas universe refresh.
Extracted from main.py to keep the main entry point lean.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from pathlib import Path
from typing import List, Dict

log = logging.getLogger("ApexTrader")

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Module-level state ─────────────────────────────────────────────────────
trending_stocks:    List[Dict] = []
last_trending_scan: float      = 0.0
last_ti_scan:       float      = 0.0
_ti_future                     = None
_ti_started_at:     float      = 0.0
_ti_warned_running: bool       = False
_ti_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


# ── Trending scan ──────────────────────────────────────────────────────────

def scan_trending_stocks(
    *,
    use_live_trending: bool,
    use_finnhub: bool,
    use_sentiment_gate: bool,
    trending_max: int,
    trending_interval_min: float,
    trending_min_momentum: float,
    priority_1: list,
) -> None:
    """Refresh ``trending_stocks`` from live feeds (Finnhub, etc.).

    Mutates the caller-supplied *priority_1* list in-place when new tickers are found,
    exactly as the original inline code did.
    """
    global trending_stocks, last_trending_scan

    if not use_live_trending and not use_finnhub:
        return

    now = time.time()
    if now - last_trending_scan < (trending_interval_min * 60):
        return

    from .utils import (
        get_trending_tickers, filter_trending_momentum,
        get_finnhub_trending_tickers, check_sentiment_gate,
    )

    try:
        log.info("Scanning for live trending stocks…")
        all_tickers: List[str] = []

        if use_live_trending:
            tickers = get_trending_tickers(trending_max)
            if tickers:
                all_tickers.extend(tickers)

        if use_finnhub:
            tickers = get_finnhub_trending_tickers()
            if tickers:
                all_tickers.extend(tickers)

        unique = list(set(all_tickers))

        if not unique:
            log.info("No trending tickers found — using existing universe")
            trending_stocks    = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                                   for s in priority_1[:trending_max]]
            last_trending_scan = now
            return

        momentum_stocks = filter_trending_momentum(unique, trending_min_momentum)

        if not momentum_stocks:
            log.info(f"No trending stocks with >{trending_min_momentum}% momentum — using universe")
            trending_stocks    = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                                   for s in priority_1[:trending_max]]
            last_trending_scan = now
            return

        if use_sentiment_gate:
            filtered = []
            for stock in momentum_stocks:
                allow, bullish_pct = check_sentiment_gate(stock["symbol"])
                if allow:
                    stock["sentiment"] = bullish_pct
                    filtered.append(stock)
            momentum_stocks = filtered
            log.info(f"Sentiment filter: {len(filtered)} passed")

        new_stocks = [s for s in momentum_stocks if s["symbol"] not in priority_1]
        if new_stocks:
            log.info(f"Found {len(new_stocks)} new trending stocks:")
            for s in new_stocks[:5]:
                log.info(f"  {s['symbol']}: +{s['momentum_pct']:.1f}% @ ${s['current_price']:.2f}")
            for s in new_stocks:
                priority_1.append(s["symbol"])
            log.info(f"Priority 1 expanded to {len(priority_1)} stocks")

        trending_stocks    = momentum_stocks
        last_trending_scan = now

    except Exception as e:
        log.error(f"Trending scan failed: {e}")
        trending_stocks = [{"symbol": s, "momentum_pct": 0, "current_price": 0}
                           for s in priority_1[:trending_max]]


# ── Trade Ideas universe refresh ───────────────────────────────────────────

def _apply_tradeideas_results(results: dict, scans: dict, priority_1: list, priority_2: list) -> None:
    """Merge TI scrape results into *priority_1* / *priority_2* lists in-place."""
    from .config import PRIORITY_1_MOMENTUM as _P1, PRIORITY_2_ESTABLISHED as _P2

    try:
        from scripts.capture_tradeideas import _is_valid_ti_ticker
    except ImportError:
        _is_valid_ti_ticker = lambda t: bool(t and len(t) <= 5)  # noqa: E731

    by_dest: dict = {
        "PRIORITY_1_MOMENTUM":   [],
        "PRIORITY_2_ESTABLISHED": [],
    }

    for scan_key, tickers in results.items():
        if scan_key in scans:
            target_list_name = scans[scan_key]["target"]
            label            = scans[scan_key]["label"]
            if target_list_name == "BOTH":
                continue
        elif scan_key.endswith("_leaders"):
            target_list_name = "PRIORITY_1_MOMENTUM"
            label            = "stock_race_central_leaders"
        elif scan_key.endswith("_laggards"):
            target_list_name = "PRIORITY_2_ESTABLISHED"
            label            = "stock_race_central_laggards"
        else:
            continue

        valid = [t for t in tickers if _is_valid_ti_ticker(t)]
        if len(valid) < 5:
            log.warning(
                f"Trade Ideas {label}: only {len(valid)} valid ticker(s) after filtering "
                f"(need ≥5) — likely a login-page scrape or empty scan; "
                f"skipping to preserve {target_list_name}"
            )
            continue
        by_dest[target_list_name].append((label, valid))

    PRIMARY_SLOTS   = 35
    SECONDARY_SLOTS = 50 - PRIMARY_SLOTS

    for target_list_name, sources in by_dest.items():
        if not sources:
            continue

        dest        = priority_1 if target_list_name == "PRIORITY_1_MOMENTUM" else priority_2
        existing_set = set(dest)

        if len(sources) == 1:
            merged = sources[0][1][:]
        else:
            seen: set = set()
            primary_part: List[str] = []
            for t in sources[0][1]:
                if len(primary_part) >= PRIMARY_SLOTS:
                    break
                if t not in seen:
                    primary_part.append(t)
                    seen.add(t)

            secondary_part: List[str] = []
            for _, src in sources[1:]:
                for t in src:
                    if len(secondary_part) >= SECONDARY_SLOTS:
                        break
                    if t not in seen:
                        secondary_part.append(t)
                        seen.add(t)
            merged = primary_part + secondary_part

        merged_set = set(merged)
        new_tickers = [t for t in merged if t not in existing_set]
        fresh       = [t for t in merged if t in existing_set]
        demote      = [t for t in dest  if t not in merged_set]

        dest.clear()
        dest.extend(merged[:50])
        for t in demote:
            if t not in merged_set and t not in dest:
                dest.append(t)

        labels = " + ".join(f"{s[0]}({len(s[1])})" for s in sources)
        if new_tickers:
            log.info(
                f"Trade Ideas [{target_list_name}] {labels}: "
                f"+{len(new_tickers)} new, {len(fresh)} existing → top-10: {merged[:10]}"
            )
        else:
            log.info(
                f"Trade Ideas [{target_list_name}] {labels}: "
                f"{len(fresh)} merged → top-10: {merged[:10]}"
            )
        log.info(
            f"── TI top-20 [{target_list_name}] "
            f"(primary={len(sources[0][1]) if sources else 0} "
            f"secondary={sum(len(s[1]) for s in sources[1:]) if len(sources) > 1 else 0}): "
            + ", ".join(dest[:20])
        )


def scan_tradeideas_universe(
    *,
    enabled: bool,
    scan_interval_min: float,
    headless: bool,
    chrome_profile,
    update_config: bool,
    priority_1: list,
    priority_2: list,
    browser: str = "edge",
    remote_debug_port: int = 9222,
) -> None:
    """Submit or check a background TI scrape; never blocks the trading cycle."""
    global last_ti_scan, _ti_future, _ti_started_at, _ti_warned_running

    if not enabled:
        return

    try:
        import sys as _sys
        _scripts = str(REPO_ROOT / "scripts")
        if _scripts not in _sys.path:
            _sys.path.insert(0, _scripts)
        from capture_tradeideas import scrape_tradeideas, SCANS
    except ImportError as e:
        log.warning(f"Trade Ideas scraper unavailable (selenium not installed?): {e}")
        last_ti_scan = time.time()
        return

    now = time.time()

    # 1) Apply finished results.
    if _ti_future is not None and _ti_future.done():
        try:
            results = _ti_future.result()
            _apply_tradeideas_results(results, SCANS, priority_1, priority_2)
        except Exception as e:
            log.error(f"Trade Ideas scan failed: {e}")
        finally:
            _ti_future         = None
            _ti_warned_running = False
            last_ti_scan       = now

    # 2) If still running, back off with escalating timeouts.
    if _ti_future is not None:
        elapsed = now - _ti_started_at
        if elapsed > 180:
            log.error(
                f"Trade Ideas scrape hard-timeout ({elapsed:.0f}s) — "
                "killing Chrome/chromedriver and resetting future"
            )
            import subprocess as _hk
            for _exe in ("chromedriver.exe", "chrome.exe"):
                try:
                    _hk.run(["taskkill", "/F", "/IM", _exe, "/T"],
                            capture_output=True, timeout=5)
                except Exception:
                    pass
            _ti_future         = None
            _ti_warned_running = False
            last_ti_scan       = now
            return
        if elapsed > 90 and not _ti_warned_running:
            log.warning(f"Trade Ideas scan still running ({elapsed:.0f}s) — trading loop continues")
            _ti_warned_running = True
        return

    # 3) Schedule next scrape when due.
    if (now - last_ti_scan) < (scan_interval_min * 60):
        return

    ti_profile  = (chrome_profile or "").strip() or None

    log.info(
        f"Scanning Trade Ideas in background (browser=edge, profile={ti_profile or 'none'}) …"
    )
    _ti_started_at     = now
    _ti_warned_running = False
    _ti_future         = _ti_executor.submit(
        scrape_tradeideas,
        update_config=update_config,
        chrome_profile=ti_profile,
        select_30min=True,
        remote_debug_port=remote_debug_port,
    )
