"""
EthicPrint — Weekly Source Finder
Per ogni brand e ogni categoria cerca nuove fonti recenti via Brave Search.
Claude Haiku valuta la pertinenza e salva le proposte in source_proposals.
Marco le revisiona e approva/rifiuta.

Gira ogni lunedì alle 9:00 UTC.
MAI inserimento automatico — tutto richiede approvazione manuale.
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
BRAVE_KEY = os.getenv("BRAVE_API_KEY")
RESEND_KEY = os.getenv("RESEND_API_KEY")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORY_LABELS = {
    "armi": "arms weapons military contracts defense",
    "ambiente": "environment CO2 emissions climate sustainability",
    "diritti": "human rights labor rights workers conditions supply chain",
    "fisco": "tax avoidance tax haven fiscal transparency",
}

# Cerca solo fonti degli ultimi 2 anni
CURRENT_YEAR = datetime.now().year
SEARCH_YEARS = f"{CURRENT_YEAR - 1}..{CURRENT_YEAR}"


async def brave_search(query: str, count: int = 5) -> list[dict]:
    if not BRAVE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_KEY},
                params={"q": query, "count": count, "search_lang": "en", "freshness": "py"},
                timeout=10,
            )
            results = r.json().get("web", {}).get("results", [])
            return [{"url": x.get("url"), "title": x.get("title"), "description": x.get("description", "")} for x in results]
    except Exception as e:
        print(f"  ⚠ Brave search failed: {e}")
        return []


async def evaluate_source(brand_name: str, category_key: str, candidate: dict) -> dict | None:
    """Chiede a Claude se il candidato è una buona fonte nuova per brand+categoria."""
    if not ANTHROPIC_KEY:
        return None
    cat_desc = CATEGORY_LABELS.get(category_key, category_key)
    prompt = f"""You are evaluating a potential NEW source for EthicPrint, an ethical brand scoring platform.

Brand: {brand_name}
Category: {category_key} ({cat_desc})
Candidate:
- URL: {candidate.get('url', '')}
- Title: {candidate.get('title', '')}
- Description: {candidate.get('description', '')}

Is this a relevant, credible, recent source about {brand_name}'s {category_key} practices?
Only approve if it's from a reputable publisher (news outlet, NGO, research institution).
Reply ONLY with JSON:
{{"relevant": true/false, "publisher": "publisher name", "summary": "1 sentence explaining relevance"}}"""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json", "").replace("```", "").strip()
            evaluated = json.loads(text)
            if evaluated.get("relevant"):
                return {**candidate, "publisher": evaluated.get("publisher", ""), "summary": evaluated.get("summary", "")}
    except Exception as e:
        print(f"  ⚠ Claude evaluation failed: {e}")
    return None


async def find_new_sources(brand: dict) -> int:
    """Cerca nuove fonti per tutte le categorie di un brand."""
    brand_name = brand["name"]
    total_proposals = 0

    for cat_key, cat_desc in CATEGORY_LABELS.items():
        query = f"{brand_name} {cat_desc} {SEARCH_YEARS}"
        print(f"  🔍 {brand_name} / {cat_key}...")

        candidates = await brave_search(query, count=5)
        for candidate in candidates:
            if not candidate.get("url"):
                continue

            # Salta se URL già presente nel DB o già proposta
            existing = supabase.table("sources").select("id").eq("url", candidate["url"]).execute()
            existing_prop = supabase.table("source_proposals").select("id").eq("url", candidate["url"]).execute()
            if existing.data or existing_prop.data:
                continue

            evaluated = await evaluate_source(brand_name, cat_key, candidate)
            if evaluated:
                supabase.table("source_proposals").insert({
                    "brand_id": brand["id"],
                    "category_key": cat_key,
                    "url": evaluated["url"],
                    "title": evaluated.get("title"),
                    "publisher": evaluated.get("publisher"),
                    "summary": evaluated.get("summary"),
                    "status": "pending",
                    "job_type": "new",
                    "replaces_id": None,
                }).execute()
                print(f"    ✅ Proposal: {evaluated['url'][:60]}")
                total_proposals += 1
                break  # Max 1 proposta per brand+categoria per settimana

            await asyncio.sleep(1)

        await asyncio.sleep(2)

    return total_proposals


async def send_notification(total_proposals: int):
    if not RESEND_KEY or not NOTIFY_EMAIL or total_proposals == 0:
        return

    proposals = supabase.table("source_proposals").select("id, url, title, publisher, brand_id, category_key, job_type")\
        .eq("status", "pending").execute().data or []

    rows = "".join(
        f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{p.get('publisher','—')}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee'>{p.get('category_key','')}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee'><a href='{p.get('url','')}'>{(p.get('title') or p.get('url',''))[:60]}</a></td></tr>"
        for p in proposals
    )

    html = f"""<div style="font-family:sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#2d7d46">📬 EthicPrint — Weekly Source Finder</h2>
  <p>Found <strong>{total_proposals} new source proposals</strong> this week. Review and approve below.</p>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th style="padding:6px;text-align:left">Publisher</th>
      <th style="padding:6px;text-align:left">Category</th>
      <th style="padding:6px;text-align:left">Source</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="margin-top:20px">
    <a href="https://web-production-14708.up.railway.app/source-proposals">Review proposals →</a>
  </p>
  <p style="color:#999;font-size:12px">EthicPrint weekly finder · {datetime.now().strftime('%Y-%m-%d')}</p>
</div>"""

    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
                json={
                    "from": "EthicPrint Finder <checker@ethicprint.org>",
                    "to": [NOTIFY_EMAIL],
                    "subject": f"EthicPrint: {total_proposals} new source proposals to review",
                    "html": html,
                },
                timeout=15,
            )
        print(f"✉ Notification sent to {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"✗ Notification failed: {e}")


async def run_finder():
    print(f"\n{'='*50}")
    print(f"EthicPrint Weekly Source Finder — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    brands_res = supabase.table("brands").select("id, name").order("name").execute()
    brands = brands_res.data or []
    print(f"Processing {len(brands)} brands\n")

    total_proposals = 0
    for brand in brands:
        print(f"\n[{brand['name']}]")
        count = await find_new_sources(brand)
        total_proposals += count
        await asyncio.sleep(3)

    print(f"\n{'='*50}")
    print(f"DONE — {total_proposals} new proposals saved")
    print(f"{'='*50}\n")

    await send_notification(total_proposals)


if __name__ == "__main__":
    asyncio.run(run_finder())
