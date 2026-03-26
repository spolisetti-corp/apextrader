import os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from engine.config import API_KEY, API_SECRET, PAPER
from engine.notifications import build_eod_report, send_email

# load .env from repo root
load_dotenv(Path(__file__).parent / '.env')

# optionally ensure notifications option is enabled
if os.getenv('USE_EMAIL_NOTIFICATIONS', 'false').lower() not in ('true', '1', 'yes'):
    raise SystemExit('USE_EMAIL_NOTIFICATIONS is disabled in .env')

# Build Alpaca client from config keys
client = TradingClient(API_KEY, API_SECRET, paper=PAPER)
account = client.get_account()
positions = client.get_all_positions()

os.environ['USE_EMAIL_NOTIFICATIONS'] = 'true'
os.environ['EMAIL_SMTP_SERVER'] = 'smtp.gmail.com'
os.environ['EMAIL_SMTP_PORT'] = '587'
os.environ['EMAIL_TO_ADDRESSES'] = 'spolisetti.archive@gmail.com,alerts@apextrader.example.com'
os.environ['EMAIL_SMTP_USER'] = 'mock_user'
os.environ['EMAIL_SMTP_PASSWORD'] = 'mock_pass'
os.environ['EMAIL_FROM_ADDRESS'] = 'mock_from@corp.com'

report = build_eod_report(
    report_date=date.today(),
    market_summary='neutral',
    account_summary={'equity':100000,'buying_power':50000,'pdt_protected':False},
    daily_pnl=100.0,
    total_trades=1,
    eod_close_summary={'closed_count':1,'failed_count':0,'closed_items':[{'symbol':'AAPL','qty':10,'strategy':'GapBreakout','pnl':25.0}]},
    positions=[]
)

class DummySMTP:
    def __init__(self, host, port, timeout=30):
        print(f'Mock SMTP init: {host}:{port}, timeout={timeout}')
    def starttls(self):
        print('Mock starttls called')
    def login(self, user, password):
        print(f'Mock login: user={user} password={password}')
    def sendmail(self, from_addr, to_addrs, msg):
        print(f'Mock sendmail: from={from_addr} to={to_addrs} len_msg={len(msg)}')
    def quit(self):
        print('Mock quit called')

with mock.patch('engine.notifications.smtplib.SMTP', DummySMTP):
    success = send_email(report['subject'], report['text'], report['html'])
    print('send_email returned', success)
