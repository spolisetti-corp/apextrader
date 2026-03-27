"""
Trade Ideas — Screenshot + Universe Updater
============================================
Navigates to two Trade Ideas TIPro scan pages with Selenium Chrome,
captures screenshots, extracts ticker symbols, and optionally patches
engine/config.py so the universe is kept current.

Pages scraped
-------------
  HIGH_SHORT_FLOAT  https://www.trade-ideas.com/TIPro/highshortfloat/
  MARKET_SCOPE_360  https://www.trade-ideas.com/TIPro/marketscope360/

Usage
-----
  # Single run — screenshot + show extracted tickers
  python scripts/capture_tradeideas.py

  # Single run AND patch config.py
  python scripts/capture_tradeideas.py --update-config

  # Loop every 5 minutes AND patch config
  python scripts/capture_tradeideas.py --loop 300 --update-config

  # Use your existing Chrome profile (already logged in to Trade-Ideas)
  python scripts/capture_tradeideas.py --chrome-profile "Default" --update-config

Requirements
------------
  pip install selenium webdriver-manager pillow
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── optional PIL for timestamp overlay ──────────────────────────
try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Selenium ─────────────────────────────────────────────────────
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

# ── Paths ────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent
OUTPUT_DIR  = REPO_ROOT / "screenshots"
CONFIG_FILE = REPO_ROOT / "engine" / "config.py"

# ── Trade Ideas scan URLs ────────────────────────────────────────
SCANS: dict[str, dict] = {
    "highshortfloat": {
        "url":    "https://www.trade-ideas.com/TIPro/highshortfloat/",
        "label":  "high_short_float",
        "target": "PRIORITY_2_ESTABLISHED",   # squeeze / short-float candidates
    },
    "marketscope360": {
        "url":    "https://www.trade-ideas.com/TIPro/marketscope360/",
        "label":  "market_scope_360",
        "target": "PRIORITY_1_MOMENTUM",      # momentum leaders
    },
}

# Words to exclude from ticker extraction (common UI/nav/HTML words)
_IGNORE = {
    "A", "AN", "AND", "OR", "NOT", "THE", "FOR", "ALL", "NEW", "NO", "PM", "AM",
    "NA", "GO", "BE", "IN", "ON", "TO", "AT", "BY", "IF", "IS", "IT", "AS", "OF",
    "MY", "US", "UP", "DO", "SO", "ME", "HE", "WE", "VS",
    # UI / nav words visible on Trade Ideas pages
    "MIN", "RACE", "PRE", "POST", "EST", "USD", "ETF", "ETH", "BTC",
    "HIGH", "LOW", "BUY", "SELL", "OPEN", "CLOSE", "MARKET", "PRICE",
    "FLOAT", "SHORT", "CHANGE", "VOLUME", "SCAN", "TRADE", "IDEAS", "SCOPE",
    "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    "NAS", "DOW", "EPS", "RSI", "SMA", "EMA", "ATR", "ADX", "MACD",
    "HOLLY", "PRO", "MY", "COPY", "WAVE", "DEEP", "DIVE", "PLAY",
    "UNUSUAL", "OPTIONS", "SECTORS", "EXPLORE", "GROUPS", "TRADING",
    "COMPETITION", "WATCHLISTS", "SETTINGS", "DASHBOARDS", "CHANNELS",
    "MOMENTUM", "WAVES", "STOCK", "SCOPE", "BIGGEST", "GAINERS", "LOSERS",
    "DELAYED", "LIVE", "ALERT", "ALERTS", "FILTER", "FILTERS",
}

_TICKER_RE = re.compile(r'\b([A-Z]{2,5})\b')

# How long to wait (seconds) for page to render
TABLE_WAIT_SEC = 20
PAGE_LOAD_SEC  = 15


# ── Selenium driver ───────────────────────────────────────────────
def _build_driver(headless: bool = False, chrome_profile: Optional[str] = None) -> "webdriver.Chrome":
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1600,900")
    else:
        opts.add_argument("--start-maximized")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    if chrome_profile:
        import os
        user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        opts.add_argument(f"--user-data-dir={user_data}")
        opts.add_argument(f"--profile-directory={chrome_profile}")

    service = ChromeService(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# ── Ticker extraction ─────────────────────────────────────────────
def _extract_tickers(driver: "webdriver.Chrome") -> list[str]:
    """
    Extract ticker symbols from the loaded Trade Ideas heatmap page.
    Primary: body.innerText scan (works for React/JS-rendered heatmaps).
    Fallback: href link pattern + data-symbol attributes.
    Returns a de-duped ordered list of up to 50 tickers.
    """
    found: list[str] = []

    # Strategy 1: body.innerText — most reliable for JS-rendered heatmap tiles
    try:
        body_text = driver.execute_script("return document.body.innerText;") or ""
        for m in _TICKER_RE.finditer(body_text):
            t = m.group(1)
            if t not in _IGNORE:
                found.append(t)
    except Exception:
        pass

    # Strategy 2: data-symbol / data-ticker / data-code attributes
    try:
        attrs = driver.execute_script("""
            var r = [];
            document.querySelectorAll('[data-symbol],[data-ticker],[data-code]').forEach(function(el){
                var v = el.getAttribute('data-symbol') || el.getAttribute('data-ticker') || el.getAttribute('data-code');
                if (v) r.push(v.toUpperCase().trim());
            });
            return r;
        """) or []
        for t in attrs:
            if _TICKER_RE.fullmatch(t) and t not in _IGNORE:
                found.append(t)
    except Exception:
        pass

    # Strategy 3: href links containing /stock/TICKER
    try:
        for anchor in driver.find_elements(By.TAG_NAME, "a"):
            href = anchor.get_attribute("href") or ""
            m = re.search(r'/stock/([A-Z]{1,5})(?:[/?]|$)', href)
            if m:
                found.append(m.group(1))
    except Exception:
        pass

    # De-dup preserving order, max 50
    seen: set[str] = set()
    clean: list[str] = []
    for t in found:
        if t not in seen and t not in _IGNORE:
            seen.add(t)
            clean.append(t)
    return clean[:50]


# ── Screenshot helper ─────────────────────────────────────────────
def _save_screenshot(driver: "webdriver.Chrome", label: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"tradeideas_{label}_{ts}.png"
    driver.save_screenshot(str(out_path))

    if PIL_OK:
        try:
            img  = Image.open(out_path)
            draw = ImageDraw.Draw(img)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f"  |  {label}"
            draw.rectangle([(0, 0), (len(stamp) * 7 + 8, 18)], fill=(0, 0, 0, 200))
            draw.text((4, 2), stamp, fill=(255, 255, 255))
            img.save(out_path)
        except Exception:
            pass

    print(f"[OK   ] screenshot → {out_path}")
    return out_path


# ── Config patcher ────────────────────────────────────────────────
def _patch_config(list_name: str, new_tickers: list[str]) -> int:
    """
    Add *new_tickers* to data/universe.json (TTL-managed) instead of patching
    config.py source code.  list_name determines the tier:
      PRIORITY_1_MOMENTUM   → tier 1 (TTL 14 days)
      PRIORITY_2_ESTABLISHED → tier 2 (TTL 30 days)
    Returns the number of *new* tickers inserted.
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT))
    from engine.universe import add_tickers  # noqa: E402

    tier = 1 if "PRIORITY_1" in list_name else 2
    added = add_tickers(new_tickers, tier=tier)
    if added:
        print(f"[UNI  ] {added} new ticker(s) added to universe.json (tier {tier}): {new_tickers[:5]}{'…' if len(new_tickers)>5 else ''}")
    return added


# ── High-short-float set patcher ────────────────────────────────
def _patch_high_short_float(new_tickers: list[str]) -> int:
    """
    Merge *new_tickers* into the HIGH_SHORT_FLOAT_STOCKS set in config.py.
    Returns the number of tickers added.
    """
    src = CONFIG_FILE.read_text(encoding="utf-8")

    # Extract current set members
    m = re.search(
        r'HIGH_SHORT_FLOAT_STOCKS\s*=\s*\{([^}]*)\}',
        src, re.DOTALL
    )
    if not m:
        print("[WARN ] Could not locate HIGH_SHORT_FLOAT_STOCKS in config.py — skipping")
        return 0

    existing = set(re.findall(r'"([A-Z]{1,5})"', m.group(1)))
    to_add   = [t for t in new_tickers if t not in existing]
    if not to_add:
        return 0

    new_members = sorted(existing | set(to_add))
    # Rebuild the set block (up to 6 per line for readability)
    lines = []
    chunk = []
    for ticker in new_members:
        chunk.append(f'"{ticker}"')
        if len(chunk) == 6:
            lines.append("    " + ", ".join(chunk) + ",")
            chunk = []
    if chunk:
        lines.append("    " + ", ".join(chunk) + ",")
    new_block = "HIGH_SHORT_FLOAT_STOCKS  = {\n" + "\n".join(lines) + "\n}"

    new_src = re.sub(
        r'HIGH_SHORT_FLOAT_STOCKS\s*=\s*\{[^}]*\}',
        new_block,
        src,
        flags=re.DOTALL,
    )
    CONFIG_FILE.write_text(new_src, encoding="utf-8")
    return len(to_add)


# ── Dropdown helper ──────────────────────────────────────────────
def _try_select_30min(driver: "webdriver.Chrome") -> bool:
    """
    Attempt to select 'Change Last 30 Min (%)' from whatever dropdown
    is present on the page.  Returns True if successful.
    """
    # Strategy 1: native <select>
    try:
        from selenium.webdriver.support.select import Select as SeleniumSelect
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            for opt in sel_el.find_elements(By.TAG_NAME, "option"):
                if "30" in opt.text and "min" in opt.text.lower():
                    SeleniumSelect(sel_el).select_by_visible_text(opt.text)
                    print(f"[OK   ] Dropdown selected (native <select>): {opt.text}")
                    return True
    except Exception:
        pass

    # Strategy 2: React custom dropdown — click trigger then option
    try:
        # Find the visible trigger that currently shows the label
        trigger = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH,
                "//*[contains(@class,'select') or contains(@class,'Select')"
                " or contains(@class,'dropdown') or contains(@class,'Dropdown')]"
                "[contains(normalize-space(.),'Change') or contains(normalize-space(.),'%')]"
            ))
        )
        trigger.click()
        time.sleep(1.5)
        option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//*[contains(text(),'30 Min') or contains(text(),'30 min')]"
            ))
        )
        print(f"[OK   ] Dropdown selected (React): {option.text}")
        option.click()
        return True
    except Exception:
        pass

    # Strategy 3: JS inject into any <select> with a 30-min option
    try:
        result = driver.execute_script("""
            var selects = document.querySelectorAll('select');
            for (var s of selects) {
                for (var o of s.options) {
                    if (o.text.includes('30') && o.text.toLowerCase().includes('min')) {
                        s.value = o.value;
                        s.dispatchEvent(new Event('change', {bubbles: true}));
                        return o.text;
                    }
                }
            }
            return null;
        """)
        if result:
            print(f"[OK   ] Dropdown selected (JS inject): {result}")
            return True
    except Exception:
        pass

    return False


# ── Main scrape function ──────────────────────────────────────────
def scrape_tradeideas(
    update_config: bool = False,
    headless: bool = False,
    chrome_profile: Optional[str] = None,
    select_30min: bool = False,
) -> dict[str, list[str]]:
    """
    Scrape both Trade Ideas scan pages.
    If select_30min=True, attempts to pick 'Change Last 30 Min (%)'
    from the heatmap dropdown before extracting tickers.
    Returns {scan_key: [tickers, …]}.
    """
    if not SELENIUM_OK:
        print("[ERROR] selenium / webdriver-manager not installed.")
        print("        Run:  pip install selenium webdriver-manager pillow")
        sys.exit(1)

    results: dict[str, list[str]] = {}
    driver = _build_driver(headless=headless, chrome_profile=chrome_profile)

    try:
        for scan_key, scan in SCANS.items():
            url   = scan["url"]
            label = scan["label"]

            print(f"\n[....] Loading {url}")
            driver.get(url)

            # Wait for body/div to appear
            for sel in ["body", "div"]:
                try:
                    WebDriverWait(driver, TABLE_WAIT_SEC).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    break
                except Exception:
                    continue

            # Grace period for React heatmap to fully render
            time.sleep(10)

            # Optionally select 'Change Last 30 Min (%)' dropdown
            if select_30min:
                found = _try_select_30min(driver)
                if not found:
                    print("[WARN ] Could not find 30-min dropdown — scraping current view")
                else:
                    time.sleep(6)   # wait for tiles to refresh after selection

            tickers = _extract_tickers(driver)
            results[scan_key] = tickers
            print(f"[OK   ] {scan_key}: {len(tickers)} tickers — {tickers[:10]}{'…' if len(tickers)>10 else ''}")

            if update_config and tickers:
                added = _patch_config(scan["target"], tickers)
                if added:
                    print(f"[OK   ] universe.json: +{added} new tickers added to tier {1 if 'PRIORITY_1' in scan['target'] else 2}")
                else:
                    print(f"[INFO ] universe.json: all tickers already present")
                # both scans → also add to tier-2 HSF universe
                hsf_added = _patch_high_short_float(tickers)
                if not hsf_added:
                    print(f"[INFO ] universe.json: HSF tickers already up to date")

            # Navigate away so the tab goes blank
            try:
                driver.get("about:blank")
            except Exception:
                pass

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("[OK   ] Browser closed.")

    return results


# ── CLI ───────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture Trade Ideas scans and optionally update the stock universe"
    )
    parser.add_argument(
        "--update-config", action="store_true",
        help="Patch engine/config.py with newly discovered tickers",
    )
    parser.add_argument(
        "--loop", type=int, metavar="SECONDS", default=0,
        help="Repeat every N seconds (0 = single shot, default)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chrome in headless mode (no visible window)",
    )
    parser.add_argument(
        "--chrome-profile", metavar="PROFILE", default=None,
        help='Use an existing Chrome profile, e.g. "Default" (keeps TI login session)',
    )
    parser.add_argument(
        "--30min", dest="select_30min", action="store_true",
        help="Select 'Change Last 30 Min (%%)' dropdown on each page before scraping",
    )
    args = parser.parse_args()

    if args.loop > 0:
        print(f"[INFO ] Loop mode — capturing every {args.loop}s. Ctrl+C to stop.")
        while True:
            scrape_tradeideas(
                update_config=args.update_config,
                headless=args.headless,
                chrome_profile=args.chrome_profile,
                select_30min=args.select_30min,
            )
            print(f"[INFO ] Sleeping {args.loop}s …")
            time.sleep(args.loop)
    else:
        scrape_tradeideas(
            update_config=args.update_config,
            headless=args.headless,
            chrome_profile=args.chrome_profile,
            select_30min=args.select_30min,
        )


if __name__ == "__main__":
    main()

