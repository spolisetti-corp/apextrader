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
    rows = "".join(
        f"<tr><td>{p.symbol}</td><td>{p.qty}</td><td>${float(p.avg_entry_price):,.2f}</td>"
        f"<td>{float(p.current_price):,.2f}</td><td>{float(p.unrealized_pl):,.2f}</td>"  # type: ignore
        f"<td>{float(p.unrealized_plpc) * 100:.2f}%</td></tr>"
        for p in positions
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
    txt.append(f"- PDT: {'Yes' if account_summary.get('pdt_protected') else 'No'}")
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
        for p in positions:
            txt.append(
                f"  - {p.symbol}: {p.qty} sh @ ${float(p.avg_entry_price):,.2f} | "
                f"Unrealized {_format_currency(float(p.unrealized_pl))} ({float(p.unrealized_plpc)*100:.2f}%)"
            )
    else:
        txt.append("  - None")

    # HTML summary
    subject_prefix = _get_env('EMAIL_SUBJECT_PREFIX', 'ApexTrader EOD Report')
    html = ["<html><body style='font-family:Arial,sans-serif;background:#f4f6fa;margin:0;padding:0;'>"]
    html.append("<div style='max-width:800px;margin:24px auto;padding:20px;background:#ffffff;border-radius:12px;box-shadow:0 1px 14px rgba(0,0,0,0.08);'>")
    html.append(f"<h1 style='margin:0;color:#0d1b2a;font-size:24px;'>{subject_prefix} - {report_date.isoformat()}</h1>")
    html.append("<p style='margin:8px 0 20px;color:#2f4f4f;font-size:14px;'>Daily briefing with account status, trade activity, and EOD closing actions.</p>")

    html.append("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:20px;'>")
    html.append(f"<div style='background:#e9f5ff;border-left:4px solid #3178c6;padding:10px;border-radius:8px;'><strong>Market</strong><br>{market_summary}</div>")
    html.append(f"<div style='background:#e6ffed;border-left:4px solid #2c9f4a;padding:10px;border-radius:8px;'><strong>Equity</strong><br>{_format_currency(float(account_summary.get('equity',0)))}</div>")
    html.append(f"<div style='background:#fff8e1;border-left:4px solid #e6a000;padding:10px;border-radius:8px;'><strong>Buying Power</strong><br>{_format_currency(float(account_summary.get('buying_power',0)))}</div>")
    html.append(f"<div style='background:#fee9f2;border-left:4px solid #d32f2f;padding:10px;border-radius:8px;'><strong>PDT</strong><br>{'Yes' if account_summary.get('pdt_protected') else 'No'}</div>")
    html.append("</div>")

    # Add flashy insights block
    html.append("<div style='background:linear-gradient(135deg, #001f3f, #0057b8);border-radius:12px;padding:16px;color:#f0f8ff;margin-bottom:20px;'>")
    html.append("<h3 style='margin:0;font-size:18px;'>✨ Market Pulse</h3>")
    html.append(f"<p style='margin:8px 0;line-height:1.45;'>Today: {market_summary}. Position count: <strong>{len(positions)}</strong>. </p>")
    html.append("<p style='margin:8px 0;font-size:13px;color:#dbeeff;'>Tomorrow outlook: Expect continued momentum in liquidity leaders and watch for possible flattening around round levels; monitor gap fades.</p>")
    html.append("</div>")

    html.append("<div style='background:#fff8f2;padding:14px;border-radius:10px;margin-bottom:20px;border:1px solid #ffdab9;'>")
    html.append(f"<h3 style='margin:0 0 8px;font-size:16px;color:#a14104;'>Daily Performance</h3>")
    html.append(f"<p style='margin:0; font-size:14px; color:#6b3b00;'>Daily P&L: <strong>{_format_currency(daily_pnl)}</strong><br>Trades Today: <strong>{total_trades}</strong></p>")
    html.append("</div>")

    # Fancy position table
    html.append("<div style='margin-bottom:20px;'><h3 style='font-size:16px;color:#223f70;margin-bottom:8px;'>Open Positions</h3>")
    html.append("<table style='width:100%;border-collapse:collapse;font-size:13px;line-height:1.3;'>")
    html.append("<thead style='background:#e6eefb;color:#082a56;'><tr><th style='padding:8px;border:1px solid #c3d2eb;'>Symbol</th><th style='padding:8px;border:1px solid #c3d2eb;'>Qty</th><th style='padding:8px;border:1px solid #c3d2eb;'>Entry</th><th style='padding:8px;border:1px solid #c3d2eb;'>Current</th><th style='padding:8px;border:1px solid #c3d2eb;'>P/L</th><th style='padding:8px;border:1px solid #c3d2eb;'>P/L %</th></tr></thead>")
    if positions:
        html.append("<tbody>")
        for idx, p in enumerate(positions):
            row_bg = '#fdfdff' if idx % 2 == 0 else '#f4f8ff'
            html.append(f"<tr style='background:{row_bg};'><td style='padding:8px;border:1px solid #e2e9f9;'>{p.symbol}</td><td style='padding:8px;border:1px solid #e2e9f9;'>{p.qty}</td><td style='padding:8px;border:1px solid #e2e9f9;'>${float(p.avg_entry_price):,.2f}</td><td style='padding:8px;border:1px solid #e2e9f9;'>${float(p.current_price):,.2f}</td><td style='padding:8px;border:1px solid #e2e9f9;'>{_format_currency(float(p.unrealized_pl))}</td><td style='padding:8px;border:1px solid #e2e9f9;'>{float(p.unrealized_plpc) * 100:.2f}%</td></tr>")
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

    html.append(_build_html_section("Open Positions", _build_positions_table(positions)))
    html.append("</body></html>")

    subject = f"{subject_prefix} - {report_date.isoformat()}"
    return {"subject": subject, "text": "\n".join(txt), "html": "\n".join(html)}


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
