import smtplib
from email.message import EmailMessage
import os

def send_admin_notification(proposal: dict):
    msg = EmailMessage()
    msg["Subject"] = f"New source proposal #{proposal['id']}"
    msg["From"] = os.getenv("SMTP_FROM")
    msg["To"] = os.getenv("ADMIN_NOTIFY_EMAIL")

    msg.set_content(f"""
New source submitted

Brand ID: {proposal.get('brand_id')}
Category: {proposal.get('category_key')}
URL: {proposal.get('url')}
Title: {proposal.get('title')}
Publisher: {proposal.get('publisher')}
Summary: {proposal.get('summary')}
Submitter: {proposal.get('submitter')}
""")

    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT"))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
        server.send_message(msg)
