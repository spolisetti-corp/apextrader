import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import List, Dict, Optional

import os

from .config import (
    USE_EMAIL_NOTIFICATIONS,
    EMAIL_SMTP_SERVER,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USER,
    EMAIL_SMTP_PASSWORD,
    EMAIL_FROM_ADDRESS,
    EMAIL_TO_ADDRESSES,
)


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _get_env(name: str, default="") -> str:
    return os.getenv(name, default).strip()


def _format_currency(value: float) -> str:
    return f"${value:,.2f}"


def _format_signal_text(signals) -> str:
    if not signals:
        return "No signals"
    lines = []
    for i, s in enumerate(signals[:3], start=1):
        lines.append(f"#{i}: {s.symbol} {s.action.upper()} ${s.price:.2f} conf={s.confidence:.0%} [{s.strategy}] {s.reason}")
    return "\n".join(lines)


def _format_signal_html(signals) -> str:
    if not signals:
        return "<p>No signals</p>"
    rows = "".join(
        f"<tr><td>{i+1}</td><td>{s.symbol}</td><td>{s.action.upper()}</td><td>${s.price:.2f}</td><td>{s.confidence:.0%}</td><td>{s.strategy}</td><td>{s.reason}</td></tr>"
        for i, s in enumerate(signals[:3])
    )
    return (
        "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>"
        "<thead><tr><th>#</th><th>Symbol</th><th>Action</th><th>Price</th><th>Confidence</th><th>Strategy</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _build_html_section(title: str, content: str) -> str:
    return f"<h2>{title}</h2>\n{content}\n"


def _build_signal_table(signals) -> str:
    if not signals:
        return "<p>No signals available.</p>"

    rows = "".join(
        f"<tr><td>{i+1}</td><td>{s.symbol}</td><td>{s.action.upper()}</td><td>${s.price:.2f}</td><td>{s.confidence:.0%}</td><td>{s.strategy}</td><td>{s.reason}</td></tr>"
        for i, s in enumerate(signals)
    )
    return (
        "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse:collapse;width:100%;'>"
        "<thead><tr><th>#</th><th>Symbol</th><th>Action</th><th>Price</th><th>Confidence</th><th>Strategy</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _build_positions_table(positions) -> str:
    if not positions:
        return "<p>No open positions at EOD.</p>"

    sorted_positions = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=True)
    rows = "".join(
        f"<tr><td>{p.symbol}</td><td>{p.qty}</td><td>${float(p.avg_entry_price):,.2f}</td>"
        f"<td>{float(p.current_price):,.2f}</td><td>{float(p.unrealized_pl):,.2f}</td>"  # type: ignore
        f"<td>{float(p.unrealized_plpc) * 100:.2f}%</td></tr>"
        for p in sorted_positions
    )
    return (
        "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse:collapse;'>"
        "<thead><tr><th>Symbol</th><th>Qty</th><th>Entry</th><th>Current</th><th>Unrealized P&L</th><th>Unrealized %</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def build_top5_report(signals, report_date: date, sentiment: str = "neutral",
                      regime: str = "bull") -> Dict[str, str]:
    subject = f"\U0001f4c8 ApexTrader Top 5 Picks \u2014 {report_date.strftime('%b %d, %Y')}"

    # Plain text
    text_lines = [
        f"ApexTrader Top 5 Scan Picks — {report_date.isoformat()}",
        f"Market Sentiment: {sentiment.upper()} | Regime: {regime.upper()}",
        "",
    ]
    text_lines.append(_format_signal_text(signals))
    text = "\n".join(text_lines)

    # Colours & icons
    _sent_color = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#d97706"}.get(sentiment.lower(), "#6b7280")
    _sent_icon  = {"bullish": "\U0001f7e2", "bearish": "\U0001f534", "neutral": "\U0001f7e1"}.get(sentiment.lower(), "\u26aa")
    _regime_color = "#16a34a" if regime.lower() == "bull" else "#dc2626"
    _regime_icon  = "\U0001f4c8" if regime.lower() == "bull" else "\U0001f4c9"

    # Strategy insight blurbs
    _strat_insight = {
        "TrendBreaker":    "Shorts trapped above key MA — squeeze in progress",
        "Sweepea":         "Liquidity swept below support, pinbar reversal forming",
        "GapBreakout":     "Gap-up continuation — momentum carrying overnight move",
        "ORB":             "Opening range cleared — intraday breakout confirmed",
        "VWAPReclaim":     "VWAP reclaimed with volume — institutional buying",
        "FloatRotation":   "Low float rotating fast — high short interest catalyst",
        "Momentum":        "Strong price momentum with volume surge backing it",
        "Technical":       "Multi-indicator confluence — RSI, MACD, MA aligned",
    }

    medals = ["\U0001f947", "\U0001f948", "\U0001f949", "\U0001f3c5", "\U0001f396\ufe0f"]
    action_colors = {"buy": "#10b981", "sell": "#f43f5e", "short": "#f43f5e"}

    cards = ""
    for i, s in enumerate(signals[:5]):
        medal  = medals[i] if i < len(medals) else f"#{i+1}"
        acolor = action_colors.get(s.action.lower(), "#3b82f6")
        conf_pct = int(s.confidence * 100)
        insight  = _strat_insight.get(s.strategy, s.reason[:60])

        # ATR stop line
        if getattr(s, "atr_stop", None):
            stop_price = round(s.price - s.atr_stop, 2)
            tp_price   = round(s.price + s.atr_stop * 2, 2)
            risk_line  = f"Stop ~${stop_price:.2f} &nbsp;·&nbsp; Target ~${tp_price:.2f} &nbsp;·&nbsp; R/R 1:2"
        else:
            stop_price = round(s.price * 0.97, 2)
            risk_line  = f"Stop ~${stop_price:.2f} (3% default)"

        cards += f"""
        <div style="background:#1e293b;border-radius:12px;padding:18px 20px;margin-bottom:14px;border-left:4px solid {acolor};box-shadow:0 2px 8px rgba(0,0,0,0.3);">
          <!-- Symbol row -->
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="font-size:20px;font-weight:900;color:#f8fafc;letter-spacing:0.5px;">{medal} {s.symbol}</span>
            <span style="background:{acolor};color:#fff;padding:4px 13px;border-radius:20px;font-size:11px;font-weight:800;letter-spacing:1px;">{s.action.upper()}</span>
          </div>
          <!-- Stats row -->
          <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;">
            <div style="background:#0f172a;border-radius:8px;padding:6px 12px;text-align:center;">
              <div style="color:#64748b;font-size:9px;letter-spacing:1px;text-transform:uppercase;">Entry</div>
              <div style="color:#f1f5f9;font-size:14px;font-weight:700;">${s.price:.2f}</div>
            </div>
            <div style="background:#0f172a;border-radius:8px;padding:6px 12px;text-align:center;">
              <div style="color:#64748b;font-size:9px;letter-spacing:1px;text-transform:uppercase;">Confidence</div>
              <div style="color:{acolor};font-size:14px;font-weight:700;">{conf_pct}%</div>
            </div>
            <div style="background:#0f172a;border-radius:8px;padding:6px 12px;text-align:center;">
              <div style="color:#64748b;font-size:9px;letter-spacing:1px;text-transform:uppercase;">Strategy</div>
              <div style="color:#38bdf8;font-size:12px;font-weight:700;">{s.strategy}</div>
            </div>
          </div>
          <!-- Confidence bar -->
          <div style="margin-bottom:10px;">
            <div style="background:#0f172a;border-radius:999px;height:5px;width:100%;overflow:hidden;">
              <div style="background:linear-gradient(90deg,{acolor}88,{acolor});height:5px;border-radius:999px;width:{conf_pct}%;transition:width 0.3s;"></div>
            </div>
          </div>
          <!-- Insight -->
          <div style="background:#0f172a;border-radius:8px;padding:8px 12px;margin-bottom:8px;">
            <div style="color:#94a3b8;font-size:11px;line-height:1.5;">💡 {insight}</div>
          </div>
          <!-- Risk line -->
          <div style="color:#475569;font-size:10px;padding-top:2px;">⚡ {risk_line}</div>
          <!-- Raw reason -->
          <div style="color:#334155;font-size:10px;margin-top:4px;font-style:italic;">{s.reason}</div>
        </div>"""

    if not signals:
        cards = "<div style='text-align:center;padding:32px;color:#475569;'>🔍 No qualifying signals this scan cycle.</div>"

    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style="margin:0;padding:0;background:#0a0f1a;font-family:'Segoe UI',system-ui,Arial,sans-serif;">
  <div style="max-width:560px;margin:24px auto;padding:0 12px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e293b 0%,#162032 100%);border-radius:14px 14px 0 0;padding:26px 24px 18px;text-align:center;border-bottom:1px solid #1e3a5f;">
      <div style="font-size:10px;color:#38bdf8;letter-spacing:3px;text-transform:uppercase;margin-bottom:6px;">ApexTrader &nbsp;·&nbsp; Automated Scan</div>
      <div style="font-size:24px;font-weight:900;color:#f8fafc;">📈 Top Picks</div>
      <div style="font-size:12px;color:#475569;margin-top:5px;">{report_date.strftime('%A, %B %d, %Y')}</div>
    </div>

    <!-- Regime + Sentiment bar -->
    <div style="background:#1e293b;padding:10px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #1e3a5f;flex-wrap:wrap;">
      <span style="font-size:13px;">{_regime_icon}</span>
      <span style="background:{_regime_color}22;color:{_regime_color};border:1px solid {_regime_color}44;padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:1px;">{regime.upper()} REGIME</span>
      <span style="color:#1e3a5f;margin:0 2px;">|</span>
      <span style="font-size:13px;">{_sent_icon}</span>
      <span style="background:{_sent_color}22;color:{_sent_color};border:1px solid {_sent_color}44;padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:1px;">{sentiment.upper()}</span>
      <span style="margin-left:auto;color:#334155;font-size:9px;">{report_date.strftime('%H:%M') if hasattr(report_date,'hour') else 'SCAN'}</span>
    </div>

    <!-- Cards -->
    <div style="background:#111827;padding:18px 14px;border-radius:0 0 14px 14px;">
      {cards}
    </div>

    <!-- Footer -->
    <div style="text-align:center;padding:14px 0 8px;">
      <span style="color:#1e3a5f;font-size:9px;letter-spacing:1px;">APEXTRADER &nbsp;·&nbsp; PAPER TRADING &nbsp;·&nbsp; {report_date.isoformat()}</span>
    </div>

  </div>
</body></html>"""

    return {"subject": subject, "text": text, "html": html}


def build_eod_report(
    report_date: date,
    market_summary: str,
    account_summary: Dict,
    daily_pnl: float,
    total_trades: int,
    eod_close_summary: Dict,
    positions,
    discovery_tickers: Optional[List[Dict]] = None,
) -> Dict[str, str]:
    # Plain text summary
    txt = []
    txt.append(f"ApexTrader EOD Report - {report_date.isoformat()}")
    txt.append("=" * 60)
    txt.append(f"Market Summary: {market_summary}")
    txt.append("")
    txt.append("Account:")
    txt.append(f"- Equity: {account_summary.get('equity')}")
    txt.append(f"- Cash/Buying Power: {account_summary.get('buying_power')}")
    txt.append("")
    txt.append(f"Daily P&L: {_format_currency(daily_pnl)}")
    txt.append(f"Trades Today: {total_trades}")
    txt.append("")
    txt.append("EOD Close Summary:")
    txt.append(f"- Closed positions: {eod_close_summary.get('closed_count', 0)}")
    txt.append(f"- Failed closes: {eod_close_summary.get('failed_count', 0)}")
    txt.append("")
    if eod_close_summary.get("closed_items"):
        txt.append("Closed Symbols:")
        for item in eod_close_summary["closed_items"]:
            txt.append(
                f"  - {item['symbol']}: {item['qty']} sh | Strategy {item['strategy']} | P&L {_format_currency(item['pnl'])}"
            )
    else:
        txt.append("No EOD close trades.")

    txt.append("")
    txt.append("Open Positions:")
    if positions:
        sorted_positions = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=True)
        for p in sorted_positions:
            txt.append(
                f"  - {p.symbol}: {p.qty} sh @ ${float(p.avg_entry_price):,.2f} | "
                f"Unrealized {_format_currency(float(p.unrealized_pl))} ({float(p.unrealized_plpc)*100:.2f}%)"
            )
    else:
        txt.append("  - None")

    txt.append("")
    txt.append("Flashy Insights:")
    top_open = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=True)[0] if positions else None
    bottom_open = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=False)[0] if positions else None
    txt.append(f"- Open positions: {len(positions)}")
    txt.append(f"- EOD closed trades: {eod_close_summary.get('closed_count',0)}")
    txt.append(f"- Daily P&L: {_format_currency(daily_pnl)}")
    if top_open:
        txt.append(f"- Top gainer: {top_open.symbol} {_format_currency(float(top_open.unrealized_pl))} ({float(top_open.unrealized_plpc)*100:.2f}%)")
    if bottom_open:
        txt.append(f"- Top loser: {bottom_open.symbol} {_format_currency(float(bottom_open.unrealized_pl))} ({float(bottom_open.unrealized_plpc)*100:.2f}%)")

    txt.append("")
    txt.append("Latest Scan Candidates:")
    if discovery_tickers:
        sorted_candidates = sorted(discovery_tickers, key=lambda t: float(t.get('momentum_pct', 0)), reverse=True)
        for t in sorted_candidates[:12]:
            symbol = t.get('symbol', 'N/A')
            mp = float(t.get('momentum_pct', 0))
            cp = float(t.get('current_price', 0)) if t.get('current_price') is not None else 0
            sentiment = t.get('sentiment', 'n/a')
            txt.append(f"  - {symbol}: momentum={mp:+.1f}% | price=${cp:,.2f} | sentiment={sentiment}")
    else:
        txt.append("  - none (no live discovery data)")

    # HTML summary
    subject_prefix = _get_env('EMAIL_SUBJECT_PREFIX', 'ApexTrader EOD Report')
    html = ["<html><body style='font-family:Arial,Helvetica,sans-serif;background:#eaf1f8;margin:0;padding:20px;color:#1b2541;'>"]
    html.append("<div style='max-width:820px;margin:0 auto;padding:20px;background:linear-gradient(145deg,#f7fbff,#dbefff);border-radius:18px;box-shadow:0 8px 26px rgba(14,33,77,0.16);border:1px solid rgba(71,114,177,0.2);'>")
    html.append(f"<h1 style='margin:0;color:#0d1b2a;font-size:24px;'>{subject_prefix} - {report_date.isoformat()}</h1>")
    html.append("<p style='margin:8px 0 20px;color:#2f4f4f;font-size:14px;'>Daily briefing with account status, trade activity, and EOD closing actions.</p>")

    html.append("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:22px;'>")
    html.append(f"<div style='background:#ffffffc0;border-left:4px solid #3c72c5;padding:14px;border-radius:12px;box-shadow:0 2px 10px rgba(46,86,139,0.12);'><strong>Market</strong><br>{market_summary}</div>")
    html.append(f"<div style='background:#ffffffc0;border-left:4px solid #2a9365;padding:14px;border-radius:12px;box-shadow:0 2px 10px rgba(28,108,67,0.12);'><strong>Equity</strong><br>{_format_currency(float(account_summary.get('equity',0)))}</div>")
    html.append(f"<div style='background:#ffffffc0;border-left:4px solid #d39500;padding:14px;border-radius:12px;box-shadow:0 2px 10px rgba(121,89,0,0.12);'><strong>Buying Power</strong><br>{_format_currency(float(account_summary.get('buying_power',0)))}</div>")
    html.append("</div>")

    # Add flashy insights block
    html.append("<div style='background:linear-gradient(135deg, #1d3f72, #2a65a3);border-radius:12px;padding:16px;color:#f7fbff;margin-bottom:20px;box-shadow:0 6px 18px rgba(19,55,103,0.2);'>")
    html.append("<h3 style='margin:0;font-size:18px;'>✨ Market Pulse</h3>")
    html.append(f"<p style='margin:8px 0;line-height:1.45;font-size:14px;'>Today: {market_summary}. Position count: <strong>{len(positions)}</strong>.</p>")
    html.append("<p style='margin:6px 0 4px;font-size:13px;color:#c7daff;'>Outlook: continue tracking momentum leaders; watch for reversals around key round levels.</p>")
    html.append("<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;'>")
    html.append(f"<span style='background:#ffffff26;padding:5px 10px;border-radius:8px;font-size:12px;'>Open positions: {len(positions)}</span>")
    html.append(f"<span style='background:#ffffff26;padding:5px 10px;border-radius:8px;font-size:12px;'>EOD closes: {eod_close_summary.get('closed_count',0)}</span>")
    html.append(f"<span style='background:#ffffff26;padding:5px 10px;border-radius:8px;font-size:12px;'>Daily P&L: {_format_currency(daily_pnl)}</span>")
    html.append("</div>")
    html.append("</div>")

    html.append("<div style='background:#fff8f2;padding:14px;border-radius:10px;margin-bottom:20px;border:1px solid #ffdab9;'>")
    html.append(f"<h3 style='margin:0 0 8px;font-size:16px;color:#a14104;'>Daily Performance</h3>")
    html.append(f"<p style='margin:0; font-size:14px; color:#6b3b00;'>Daily P&L: <strong>{_format_currency(daily_pnl)}</strong><br>Trades Today: <strong>{total_trades}</strong></p>")
    html.append("</div>")

    # Flashy insights summary
    top_open = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=True)[0] if positions else None
    bottom_open = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=False)[0] if positions else None
    total_open = len(positions)
    closed = eod_close_summary.get('closed_count', 0)

    html.append("<div style='background:linear-gradient(135deg, #ff6b6b, #fca311);color:#fff;padding:14px;border-radius:12px;margin-bottom:20px;border:1px solid #e2962d;'>")
    html.append("<h3 style='margin:0 0 8px;font-size:16px;'>🚀 Flashy Insights</h3>")
    html.append(f"<p style='margin:0;font-size:13px;'>Open positions: <strong>{total_open}</strong> | EOD closes: <strong>{closed}</strong> | Daily P&L: <strong>{_format_currency(daily_pnl)}</strong></p>")
    if top_open:
        html.append(f"<p style='margin:6px 0 0;font-size:13px;'>Top gainer: <strong>{top_open.symbol}</strong> {_format_currency(float(top_open.unrealized_pl))} ({float(top_open.unrealized_plpc)*100:.2f}%)</p>")
    if bottom_open:
        html.append(f"<p style='margin:6px 0 0;font-size:13px;'>Top loser: <strong>{bottom_open.symbol}</strong> {_format_currency(float(bottom_open.unrealized_pl))} ({float(bottom_open.unrealized_plpc)*100:.2f}%)</p>")
    html.append("</div>")

    html.append("<div style='background:linear-gradient(135deg, #27496d, #3a86ff);color:#fdfdff;padding:14px;border-radius:14px;border:1px solid #4d7fc9;margin-bottom:16px; box-shadow:0 4px 18px rgba(35,102,191,0.2);'>")
    html.append("<h3 style='margin:0 0 8px;font-size:16px;'>🔥 Latest Scrape/Discovery Candidates</h3>")
    if discovery_tickers:
        html.append("<ul style='margin:0;padding-left:20px;color:#f1f5ff;font-size:13px;'>")
        sorted_candidates = sorted(discovery_tickers, key=lambda t: float(t.get('momentum_pct', 0)), reverse=True)
        for t in sorted_candidates[:12]:
            symbol = t.get('symbol', 'N/A')
            mp = float(t.get('momentum_pct', 0))
            cp = float(t.get('current_price', 0)) if t.get('current_price') is not None else 0
            sentiment = t.get('sentiment', 'n/a')
            html.append(f"<li style='margin-bottom:4px;'><strong>{symbol}</strong> — {mp:+.1f}% | ${cp:,.2f} | sentiment: {sentiment}</li>")
        html.append("</ul>")
    else:
        html.append("<p style='margin:0;color:#c5d6ff;font-size:13px;'>No recent discovery tickers available.</p>")
    html.append("</div>")

    # Fancy position table
    html.append("<div style='margin-bottom:20px;'><h3 style='font-size:16px;color:#1a3960;margin-bottom:10px;'>Open Positions</h3>")
    html.append("<table style='width:100%;border-collapse:separate;border-spacing:0 4px;font-size:13px;line-height:1.4;background:#f8fbff;border-radius:10px;overflow:hidden;'>")
    html.append("<thead style='background:#e0ecfc;color:#0f3057;'><tr><th style='padding:10px 12px;border:none;text-align:left;'>Symbol</th><th style='padding:10px 12px;border:none;text-align:right;'>Qty</th><th style='padding:10px 12px;border:none;text-align:right;'>Entry</th><th style='padding:10px 12px;border:none;text-align:right;'>Current</th><th style='padding:10px 12px;border:none;text-align:right;'>P/L</th><th style='padding:10px 12px;border:none;text-align:right;'>P/L %</th></tr></thead>")
    if positions:
        sorted_positions = sorted(positions, key=lambda p: float(p.unrealized_pl), reverse=True)
        html.append("<tbody>")
        for idx, p in enumerate(sorted_positions):
            row_bg = '#fdfdff' if idx % 2 == 0 else '#f4f8ff'
            pl_value = float(p.unrealized_pl)
            pl_color = '#118032' if pl_value >= 0 else '#b00000'
            val_pct = float(p.unrealized_plpc) * 100
            html.append(f"<tr style='background:{row_bg};'><td style='padding:8px;border:1px solid #e2e9f9;'>{p.symbol}</td><td style='padding:8px;border:1px solid #e2e9f9;'>{p.qty}</td><td style='padding:8px;border:1px solid #e2e9f9;'>${float(p.avg_entry_price):,.2f}</td><td style='padding:8px;border:1px solid #e2e9f9;'>${float(p.current_price):,.2f}</td><td style='padding:8px;border:1px solid #e2e9f9;color:{pl_color};font-weight:600;'>{_format_currency(pl_value)}</td><td style='padding:8px;border:1px solid #e2e9f9;color:{pl_color};font-weight:600;'>{val_pct:.2f}%</td></tr>")
        html.append("</tbody>")
    else:
        html.append("<tbody><tr><td colspan='6' style='padding:8px;border:1px solid #e2e9f9;text-align:center;color:#667089;'>No open positions</td></tr></tbody>")
    html.append("</table></div>")

    eod_html_lines = [f"<li>{i['symbol']} ({i['qty']} sh, {i['strategy']}) P&L {_format_currency(i['pnl'])}</li>" for i in eod_close_summary.get('closed_items', [])]
    if eod_html_lines:
        eod_html = "<ul>" + "".join(eod_html_lines) + "</ul>"
    else:
        eod_html = "<p>No EOD close trades</p>"
    html.append(_build_html_section("EOD Close Trades", eod_html))

    # Avoid duplicate open positions table; already included above in fancy section
    html.append("</body></html>")

    subject = f"{subject_prefix} - {report_date.isoformat()}"
    return {"subject": subject, "text": "\n".join(txt), "html": "\n".join(html)}


def send_email(subject: str, text: str, html: Optional[str] = None) -> bool:
    if not _bool_env('USE_EMAIL_NOTIFICATIONS', 'false') and not USE_EMAIL_NOTIFICATIONS:
        return False

    env_to = [a.strip() for a in _get_env('EMAIL_TO_ADDRESSES', '').split(',') if a.strip()]
    to_addresses = env_to or EMAIL_TO_ADDRESSES
    if not to_addresses:
        raise ValueError("No EMAIL_TO_ADDRESSES configured")

    from_address = _get_env('EMAIL_FROM_ADDRESS', EMAIL_FROM_ADDRESS or EMAIL_SMTP_USER)
    if not from_address:
        raise ValueError("No EMAIL_FROM_ADDRESS configured")

    smtp_server = _get_env('EMAIL_SMTP_SERVER', EMAIL_SMTP_SERVER or 'smtp.gmail.com')
    smtp_port = int(_get_env('EMAIL_SMTP_PORT', str(EMAIL_SMTP_PORT or 587)))
    smtp_user = _get_env('EMAIL_SMTP_USER', EMAIL_SMTP_USER)
    smtp_pass = _get_env('EMAIL_SMTP_PASSWORD', EMAIL_SMTP_PASSWORD)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = ', '.join(to_addresses)

    msg.attach(MIMEText(text, 'plain'))
    if html:
        msg.attach(MIMEText(html, 'html'))

    print(f"[DEBUG] send_email called: subject={subject}")
    print(f"[DEBUG] to={to_addresses}")
    print(f"[DEBUG] from={from_address}")
    print(f"[DEBUG] smtp_server={smtp_server} smtp_port={smtp_port} smtp_user={smtp_user}")
    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
    try:
        server.starttls()
        print("[DEBUG] starttls successful")
        server.login(smtp_user, smtp_pass)
        print("[DEBUG] SMTP login successful")
        server.sendmail(from_address, to_addresses, msg.as_string())
        print("[DEBUG] sendmail successful")
    except Exception as e:
        print(f"[DEBUG] sendmail error: {type(e).__name__} {e}")
        raise
    finally:
        server.quit()
        print("[DEBUG] SMTP connection closed")

    return True
