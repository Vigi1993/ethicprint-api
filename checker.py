"""
EthicPrint — Daily Source Checker
1. Verifica tutte le fonti: broken? contenuto mancante?
2. Per le fonti rotte cerca sostituti via Brave Search + Claude Haiku
3. Salva proposte in source_proposals per revisione manuale
4. Notifica via email se ci sono problemi o nuove proposte

Gira ogni giorno alle 8:00 UTC.
MAI modifica automatica — tutto richiede approvazione manuale.
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EthicPrint-Checker/1.0; +https://ethicprint.org)",
}
TIMEOUT = 15

CATEGORY_LABELS = {
    "armi": "arms, weapons, military contracts, defense",
    "ambiente": "environment, CO2 emissions, climate, sustainability",
    "diritti": "human rights, labor rights, workers conditions",
    "fisco": "tax avoidance, tax haven, fiscal transparency",
}


# ─── FETCH & CHECK ───────────────────────────────────────────

async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[bool, bool, str | None]:
    try:
        r = await client.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code == 404:
            return True, False, None
        if r.status_code in (403, 429, 503):
            return False, True, None
        if r.status_code >= 400:
            return True, False, None
        return False, False, r.text[:8000]
    except httpx.TimeoutException:
        return True, False, None
    except Exception:
        return False, True, None


async def check_content(source: dict, page_content: str) -> bool:
    if not ANTHROPIC_KEY:
        return False
    prompt = f"""You are checking if a web page still contains its original article.
Source: {source.get('title','N/A')} — {source.get('publisher','N/A')} ({source.get('published_at','N/A')})
URL: {source.get('url','')}
Page content (truncated): {page_content}
Reply ONLY with JSON: {{"content_present": true/false, "reason": "brief explanation"}}
If page shows 404, paywall, cookie wall only, or unrelated content: content_present = false."""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 150, "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            return not json.loads(text).get("content_present", True)
    except Exception as e:
        print(f"  ⚠ Claude content check failed: {e}")
        return False


async def check_source(client: httpx.AsyncClient, source: dict) -> dict | None:
    url = source.get("url", "")
    print(f"  [{source['id']}] {url[:60]}...")
    broken, blocked, content = await fetch_page(client, url)
    if blocked:
        print(f"    → 🚫 BLOCKED")
        return None
    content_missing = False
    if not broken and content:
        content_missing = await check_content(source, content)
    status = "✗ BROKEN" if broken else ("⚠ CONTENT MISSING" if content_missing else "✓ OK")
    print(f"    → {status}")
    return {
        "id": source["id"],
        "broken": broken,
        "content_missing": content_missing,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


# ─── BRAVE SEARCH + PROPOSAL ─────────────────────────────────

async def brave_search(query: str, count: int = 3) -> list[dict]:
    if not BRAVE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_KEY},
                params={"q": query, "count": count, "search_lang": "en"},
                timeout=10,
            )
            results = r.json().get("web", {}).get("results", [])
            return [{"url": x.get("url"), "title": x.get("title"), "description": x.get("description","")} for x in results]
    except Exception as e:
        print(f"  ⚠ Brave search failed: {e}")
        return []


async def evaluate_source(brand_name: str, category_key: str, candidate: dict) -> dict | None:
    """Chiede a Claude se il candidato è una buona fonte per brand+categoria."""
    if not ANTHROPIC_KEY:
        return None
    cat_desc = CATEGORY_LABELS.get(category_key, category_key)
    prompt = f"""You are evaluating a potential source for EthicPrint, an ethical brand scoring platform.

Brand: {brand_name}
Category: {category_key} ({cat_desc})
Candidate source:
- URL: {candidate.get('url','')}
- Title: {candidate.get('title','')}
- Description: {candidate.get('description','')}

Is this a relevant, credible source that supports scoring {brand_name} on {category_key}?
Reply ONLY with JSON:
{{"relevant": true/false, "publisher": "publisher name", "summary": "1 sentence why relevant or not"}}"""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            evaluated = json.loads(text)
            if evaluated.get("relevant"):
                return {**candidate, "publisher": evaluated.get("publisher",""), "summary": evaluated.get("summary","")}
    except Exception as e:
        print(f"  ⚠ Claude evaluation failed: {e}")
    return None


async def find_replacement(brand: dict, source: dict) -> bool:
    """Cerca un sostituto per una fonte rotta e lo propone."""
    brand_name = brand["name"]
    cat = source["category_key"]
    cat_desc = CATEGORY_LABELS.get(cat, cat)
    query = f"{brand_name} {cat_desc} report investigation news"
    print(f"    🔍 Searching replacement for [{source['id']}] {brand_name} / {cat}...")

    candidates = await brave_search(query, count=5)
    found = 0
    for candidate in candidates:
        if not candidate.get("url"):
            continue
        # Salta se URL già presente nel DB
        existing = supabase.table("sources").select("id").eq("url", candidate["url"]).execute()
        existing_prop = supabase.table("source_proposals").select("id").eq("url", candidate["url"]).execute()
        if existing.data or existing_prop.data:
            continue

        evaluated = await evaluate_source(brand_name, cat, candidate)
        if evaluated:
            supabase.table("source_proposals").insert({
                "brand_id": brand["id"],
                "category_key": cat,
                "url": evaluated["url"],
                "title": evaluated.get("title"),
                "publisher": evaluated.get("publisher"),
                "summary": evaluated.get("summary"),
                "status": "pending",
                "job_type": "replacement",
                "replaces_id": source["id"],
            }).execute()
            print(f"    ✅ Proposal saved: {evaluated['url'][:60]}")
            found += 1
            if found >= 2:  # Max 2 proposte per fonte rotta
                break
        await asyncio.sleep(1)
    return found > 0


# ─── NOTIFICATION ─────────────────────────────────────────────

async def send_notification(stats: dict):
    if not RESEND_KEY or not NOTIFY_EMAIL:
        print("⚠ RESEND_API_KEY or NOTIFY_EMAIL not set — skipping notification")
        return

    issues = supabase.table("sources").select("id,url,title,publisher,broken,content_missing,brand_id")        .or_("broken.eq.true,content_missing.eq.true").execute().data or []
    proposals = supabase.table("source_proposals").select("id,url,title,publisher,brand_id,job_type")        .eq("status","pending").execute().data or []

    if not issues and not proposals:
        return

    issue_rows = "".join(f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{'🔴 Broken' if s.get('broken') else '⚠️ Missing'}</td><td style='padding:6px;border-bottom:1px solid #eee'>{s.get('publisher','—')}</td><td style='padding:6px;border-bottom:1px solid #eee'><a href='{s.get('url','')}'>{(s.get('title') or s.get('url',''))[:60]}</a></td></tr>" for s in issues)
    prop_rows = "".join(f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{p.get('publisher','—')}</td><td style='padding:6px;border-bottom:1px solid #eee'><a href='{p.get('url','')}'>{(p.get('title') or p.get('url',''))[:60]}</a></td><td style='padding:6px;border-bottom:1px solid #eee'>{p.get('job_type','')}</td></tr>" for p in proposals)

    html = f"""<div style="font-family:sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#e53e3e">⚠️ EthicPrint — Daily Report</h2>
  <p>✓ {stats['ok']} OK · ✗ {stats['broken']} broken · ⚠ {stats['content_missing']} missing · 🚫 {stats.get('blocked',0)} blocked</p>
  {"<h3>Source issues</h3><table style='width:100%;border-collapse:collapse'><thead><tr><th style='padding:6px;text-align:left'>Status</th><th style='padding:6px;text-align:left'>Publisher</th><th style='padding:6px;text-align:left'>Source</th></tr></thead><tbody>" + issue_rows + "</tbody></table>" if issues else ""}
  {"<h3>📬 Proposals to review (" + str(len(proposals)) + ")</h3><table style='width:100%;border-collapse:collapse'><thead><tr><th style='padding:6px;text-align:left'>Publisher</th><th style='padding:6px;text-align:left'>URL</th><th style='padding:6px;text-align:left'>Type</th></tr></thead><tbody>" + prop_rows + "</tbody></table>" if proposals else ""}
  <p style="margin-top:20px"><a href="https://web-production-14708.up.railway.app/sources/issues">View issues →</a> &nbsp; <a href="https://web-production-14708.up.railway.app/source-proposals">View proposals →</a></p>
  <p style="color:#999;font-size:12px">EthicPrint daily checker · {datetime.now().strftime('%Y-%m-%d')}</p>
</div>"""

    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
                json={
                    "from": "EthicPrint Checker <checker@ethicprint.org>",
                    "to": [NOTIFY_EMAIL],
                    "subject": f"EthicPrint: {stats['broken']} broken · {len(proposals)} proposals pending",
                    "html": html,
                },
                timeout=15,
            )
        print(f"✉ Notification sent to {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"✗ Notification failed: {e}")


# ─── MAIN ─────────────────────────────────────────────────────

async def run_checker():
    print(f"\n{'='*50}")
    print(f"EthicPrint Daily Checker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Carica tutte le fonti con info brand
    sources_res = supabase.table("sources").select("id, url, title, publisher, published_at, category_key, brand_id, brands(id, name)").execute()
    sources = sources_res.data or []
    print(f"Found {len(sources)} sources\n")

    stats = {"ok": 0, "broken": 0, "content_missing": 0, "blocked": 0, "errors": 0}
    broken_sources = []

    async with httpx.AsyncClient() as client:
        for source in sources:
            try:
                checked = await check_source(client, source)
                if checked is None:
                    stats["blocked"] += 1
                    await asyncio.sleep(1)
                    continue

                supabase.table("sources").update({
                    "broken": checked["broken"],
                    "content_missing": checked["content_missing"],
                    "last_checked": checked["last_checked"],
                }).eq("id", checked["id"]).execute()

                if checked["broken"]:
                    stats["broken"] += 1
                    broken_sources.append(source)
                elif checked["content_missing"]:
                    stats["content_missing"] += 1
                    broken_sources.append(source)
                else:
                    stats["ok"] += 1

                await asyncio.sleep(1)
            except Exception as e:
                print(f"  ✗ Error on source {source.get('id')}: {e}")
                stats["errors"] += 1

    # Cerca sostituti per le fonti rotte
    if broken_sources and BRAVE_KEY:
        print(f"\n--- Searching replacements for {len(broken_sources)} broken sources ---\n")
        for source in broken_sources:
            brand = source.get("brands") or {}
            if brand:
                await find_replacement(brand, source)
            await asyncio.sleep(2)

    print(f"\n{'='*50}")
    print(f"DONE — ✓ {stats['ok']} OK · ✗ {stats['broken']} broken · ⚠ {stats['content_missing']} missing · 🚫 {stats['blocked']} blocked · {stats['errors']} errors")
    print(f"{'='*50}\n")

    await send_notification(stats)


if __name__ == "__main__":
    asyncio.run(run_checker())
