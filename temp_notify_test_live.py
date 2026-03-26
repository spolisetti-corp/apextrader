from datetime import date
from dotenv import load_dotenv
from pathlib import Path
import importlib

# Load .env values first
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

from alpaca.trading.client import TradingClient
import engine.config as cfg
import engine.notifications as nt
importlib.reload(cfg)
importlib.reload(nt)

from engine.config import API_KEY, API_SECRET, PAPER, USE_EMAIL_NOTIFICATIONS
from engine.notifications import build_eod_report, send_email

if not USE_EMAIL_NOTIFICATIONS:
    raise SystemExit('USE_EMAIL_NOTIFICATIONS is disabled in config')

client = TradingClient(API_KEY, API_SECRET, paper=PAPER)
account = client.get_account()
positions = client.get_all_positions()

report = build_eod_report(
    report_date=date.today(),
    market_summary='live',
    account_summary={
        'equity': float(account.equity),
        'buying_power': float(account.buying_power),
        'pdt_protected': account.pattern_day_trader,
    },
    daily_pnl=0.0,
    total_trades=0,
    eod_close_summary={'closed_count':0,'failed_count':0,'closed_items':[]},
    positions=positions
)

print('Subject:', report['subject'])
print('Positions:', len(positions))

try:
    sent = send_email(report['subject'], report['text'], report['html'])
    print('send_email returned', sent)
except Exception as e:
    print('send_email exception:', type(e).__name__, e)
