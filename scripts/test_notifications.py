"""ApexTrader notification smoke test.
Run with:
  python scripts/test_notifications.py
Requirements:
  - .env SMTP vars configured
  - USE_EMAIL_NOTIFICATIONS=true

This script runs a single send_email() call and prints outcome.
"""

import os
from engine.notifications import send_email

# Ensure flag active in current process
os.environ["USE_EMAIL_NOTIFICATIONS"] = "true"

subject = "ApexTrader Notification Smoke Test"
text = "This is a test plain-text email. If you got this, notifications are working."
html = "<p>This is a test <strong>HTML</strong> email.</p>"

print("USE_EMAIL_NOTIFICATIONS:", os.getenv("USE_EMAIL_NOTIFICATIONS"))
print("EMAIL_SMTP_SERVER:", os.getenv("EMAIL_SMTP_SERVER"))
print("EMAIL_SMTP_PORT:", os.getenv("EMAIL_SMTP_PORT"))
print("EMAIL_SMTP_USER:", os.getenv("EMAIL_SMTP_USER"))
print("EMAIL_FROM_ADDRESS:", os.getenv("EMAIL_FROM_ADDRESS"))
print("EMAIL_TO_ADDRESSES:", os.getenv("EMAIL_TO_ADDRESSES"))

try:
    result = send_email(subject, text, html)
    print("send_email returned", result)
except Exception as exc:
    print("send_email failed:", type(exc).__name__, exc)
