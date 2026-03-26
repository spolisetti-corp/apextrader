import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import List, Dict, Optional

import os


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _get_env(name: str, default="") -> str:
    return os.getenv(name, default).strip()


def _format_currency(value: float) -> str:
    return f"${value:,.2f}"


def _build_html_section(title: str, content: str) -> str:
    return f"<h2>{title}</h2>\n{content}\n"


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


def _format_top_signals_html(highlight_signals) -> str:
    if not highlight_signals:
        return "<p style='margin:0;color:#667089;'>No signals today.</p>"

    rows = []
    for idx, sig in enumerate(highlight_signals, 1):
        rows.append(
            f"<tr><td>#{idx}</td><td>{sig.symbol}</td><td>{sig.action}</td><td>${sig.price:,.2f}</td>"
            f"<td>{sig.confidence*100:.0f}%</td><td>{sig.strategy}</td></tr>"
        )
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr><th style='border:1px solid #c3d2eb;padding:8px;'>Rank</th>"
        "<th style='border:1px solid #c3d2eb;padding:8px;'>Ticker</th>"
        "<th style='border:1px solid #c3d2eb;padding:8px;'>Action</th>"
        "<th style='border:1px solid #c3d2eb;padding:8px;'>Price</th>"
        "<th style='border:1px solid #c3d2eb;padding:8px;'>Conf</th>"
        "<th style='border:1px solid #c3d2eb;padding:8px;'>Strategy</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_scan_summary_report(
    report_date: date,
    cycle_name: str,
    scan_count: int,
    signals_count: int,
    executed_count: int,
    top_signals,
    discovery_tickers=None,
) -> Dict[str, str]:
    txt = []
    txt.append(f"ApexTrader Scan Summary - {report_date.isoformat()} ({cycle_name})")
    txt.append("=" * 60)
    txt.append(f"Scanned symbols: {scan_count}")
    txt.append(f"Signals found: {signals_count}")
    txt.append(f"Orders executed: {executed_count}")
    txt.append("")
    txt.append("Top 3 signals:")
    if top_signals:
        for idx, sig in enumerate(top_signals, 1):
            txt.append(f"  #{idx} {sig.symbol} {sig.action} ${sig.price:,.2f} conf={sig.confidence*100:.0f}% [{sig.strategy}]")
    else:
        txt.append("  none")
    if discovery_tickers:
        txt.append("")
        txt.append("Latest discovery tickers:")
        txt.append(", ".join([t.get('symbol', 'N/A') for t in discovery_tickers[:8]]))

    subject = f"ApexTrader Scan Summary - {report_date.isoformat()}"
    html = ["<html><body style='font-family:Arial,sans-serif;background:#f2f3f7;margin:0;padding:20px;'>"]
    html.append("<div style='max-width:760px;margin:auto;background:#ffffff;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,0.08);padding:18px;'>")
    html.append(f"<h2 style='margin-top:0;color:#1a2f4d;'>ApexTrader Scan Summary ({cycle_name})</h2>")
    html.append(f"<p style='color:#4f6272;'>Scanned symbols: <strong>{scan_count}</strong> | Signals: <strong>{signals_count}</strong> | Executed: <strong>{executed_count}</strong></p>")
    html.append("<h3 style='margin:12px 0 8px;color:#2d4f81;'>Top 3 signals</h3>")
    html.append(_format_top_signals_html(top_signals))

    if discovery_tickers:
        html.append("<h3 style='margin:14px 0 8px;color:#2d4f81;'>Discovery Snapshot</h3>")
        html.append("<p style='margin:0 0 8px;color:#556a84;font-size:13px;'>Latest candidates from discovery sources</p>")
        discovery_list = [t.get('symbol', 'N/A') for t in discovery_tickers[:10]]
        html.append(f"<p style='margin:0;color:#2b3d60;font-size:14px;font-weight:600;'>{', '.join(discovery_list)}</p>")

    html.append("</div></body></html>")
    return {"subject": subject, "text": "\n".join(txt), "html": "\n".join(html)}


def send_scan_summary_email(report_date: date, cycle_name: str, scan_count: int,
                            signals_count: int, executed_count: int,
                            top_signals, discovery_tickers=None):
    report = build_scan_summary_report(
        report_date=report_date,
        cycle_name=cycle_name,
        scan_count=scan_count,
        signals_count=signals_count,
        executed_count=executed_count,
        top_signals=top_signals,
        discovery_tickers=discovery_tickers,
    )

    # Non-blocking: send in background
    import threading
    thread = threading.Thread(
        target=send_email,
        args=(report['subject'], report['text'], report['html']),
        kwargs={},
        daemon=True,
    )
    thread.start()


def send_email(subject: str, text: str, html: Optional[str] = None) -> bool:
    if not _bool_env('USE_EMAIL_NOTIFICATIONS', 'false'):
        return False

    to_addresses = [a.strip() for a in _get_env('EMAIL_TO_ADDRESSES').split(',') if a.strip()]
    if not to_addresses:
        raise ValueError("No EMAIL_TO_ADDRESSES configured")

    from_address = _get_env('EMAIL_FROM_ADDRESS', _get_env('EMAIL_SMTP_USER', ''))
    if not from_address:
        raise ValueError("No EMAIL_FROM_ADDRESS configured")

    smtp_server = _get_env('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(_get_env('EMAIL_SMTP_PORT', '587'))
    smtp_user = _get_env('EMAIL_SMTP_USER', '')
    smtp_pass = _get_env('EMAIL_SMTP_PASSWORD', '')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = ', '.join(to_addresses)

    msg.attach(MIMEText(text, 'plain'))
    if html:
        msg.attach(MIMEText(html, 'html'))

    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
    try:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_address, to_addresses, msg.as_string())
    finally:
        server.quit()

    return True


    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
    try:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_address, to_addresses, msg.as_string())
    finally:
        server.quit()

    return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM_ADDRESS
    msg["To"] = ", ".join(EMAIL_TO_ADDRESSES)

    msg.attach(MIMEText(text, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))

    server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30)
    try:
        server.starttls()
        server.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM_ADDRESS, EMAIL_TO_ADDRESSES, msg.as_string())
    finally:
        server.quit()

    return True
