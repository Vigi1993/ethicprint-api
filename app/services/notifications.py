import os
from datetime import datetime

import httpx


async def notify_contribution(type: str, data: dict):
    resend_key = os.getenv("RESEND_KEY")
    notify_email = os.getenv("NOTIFY_EMAIL")

    if not resend_key or not notify_email:
        return

    icons = {
        "brand": "🏷️",
        "source": "🔗",
        "error": "🚨",
    }

    titles = {
        "brand": "New brand proposal",
        "source": "New source proposal",
        "error": "New error report",
    }

    icon = icons.get(type, "📬")
    title = titles.get(type, "New contribution")

    rows = ""
    for key, val in data.items():
        if val:
            rows += f"""
<tr>
<td style='padding:6px 10px;color:#666;font-size:12px;white-space:nowrap'>{key}</td>
<td style='padding:6px 10px;font-size:12px'>{val}</td>
</tr>
"""

    html = f"""
<div style="font-family:sans-serif;max-width:560px;margin:0 auto;color:#1a1a2e">
  <div style="background:#0f1a14;padding:18px 24px;border-radius:12px 12px 0 0;border-bottom:2px solid #63CAB7">
    <h2 style="color:#63CAB7;margin:0;font-size:16px;font-weight:600">{icon} EthicPrint — {title}</h2>
    <p style="color:rgba(255,255,255,0.4);margin:4px 0 0;font-size:12px">
      {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
    </p>
  </div>

  <div style="background:#fff;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 12px 12px;padding:20px">
    <table style="width:100%;border-collapse:collapse;background:#f9f9f9;border-radius:8px;overflow:hidden">
      {rows}
    </table>

    <div style="margin-top:20px;text-align:center">
      <a href="https://ethicprint.org/admin.html"
         style="display:inline-block;background:#0f1a14;color:#63CAB7;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;border:1px solid #63CAB7">
        Review in admin →
      </a>
    </div>
  </div>
</div>
"""

    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "EthicPrint <checker@ethicprint.org>",
                    "to": [notify_email],
                    "subject": f"EthicPrint: {title}",
                    "html": html,
                },
                timeout=10,
            )
    except Exception as e:
        print(f"notify_contribution failed: {e}")
