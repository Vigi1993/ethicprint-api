"""
EthicPrint — Weekly Source Checker
Verifica tutte le fonti in sources:
1. Check tecnico: la URL risponde?
2. Check contenuto: Claude legge la pagina e verifica che l'articolo sia ancora presente

Eseguito come cron job su Railway (ogni lunedì).
MAI modifica automatica ai punteggi — solo flag per revisione manuale.
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

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EthicPrint-Checker/1.0; +https://ethicprint.org)",
}

TIMEOUT = 15  # secondi


async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[bool, bool, str | None]:
    """
    Ritorna (broken, blocked, content).
    broken=True solo per 404 o errori di rete reali (pagina sparita).
    blocked=True per 403/429/503 (sito blocca bot ma la pagina esiste).
    content=testo HTML troncato se disponibile.
    """
    try:
        r = await client.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code == 404:
            return True, False, None  # Pagina davvero sparita
        if r.status_code in (403, 429, 503):
            return False, True, None  # Sito blocca bot — non possiamo verificare
        if r.status_code >= 400:
            return True, False, None  # Altro errore — considera rotto
        return False, False, r.text[:8000]
    except httpx.TimeoutException:
        return True, False, None  # Timeout — considera rotto
    except Exception:
        return False, True, None  # Errore generico — non possiamo verificare


async def check_content(source: dict, page_content: str) -> bool:
    """
    Chiede a Claude se il contenuto originale dell'articolo è ancora presente.
    Ritorna True se il contenuto risulta mancante/rimosso.
    """
    if not ANTHROPIC_KEY:
        return False

    prompt = f"""You are checking if a web page still contains its original article.

Source info:
- Title: {source.get('title', 'N/A')}
- Publisher: {source.get('publisher', 'N/A')}
- Published: {source.get('published_at', 'N/A')}
- URL: {source.get('url', '')}

Page content (truncated):
{page_content}

Does this page still contain the original article described above?
Reply with ONLY a JSON object: {{"content_present": true/false, "reason": "brief explanation"}}
If the page shows a 404 message, paywall block, redirect to homepage, cookie wall only, or unrelated content, content_present should be false."""

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            data = r.json()
            text = data["content"][0]["text"].strip()
            # Rimuovi eventuali backtick
            text = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            return not parsed.get("content_present", True)
    except Exception as e:
        print(f"  ⚠ Claude check failed: {e}")
        return False


async def check_source(client: httpx.AsyncClient, source: dict) -> dict:
    """Controlla una singola fonte e ritorna i campi aggiornati."""
    url = source.get("url", "")
    print(f"  Checking [{source['id']}] {url[:60]}...")

    broken, blocked, content = await fetch_page(client, url)
    content_missing = False

    if blocked:
        # Non possiamo verificare — lasciamo i valori precedenti invariati
        print(f"    → 🚫 BLOCKED (bot protection — skipping)")
        return None  # Segnale per saltare l'aggiornamento

    if not broken and content:
        content_missing = await check_content(source, content)

    result = {
        "id": source["id"],
        "broken": broken,
        "content_missing": content_missing,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }

    status = "✓ OK"
    if broken:
        status = "✗ BROKEN (404)"
    elif content_missing:
        status = "⚠ CONTENT MISSING"
    print(f"    → {status}")

    return result


async def run_checker():
    print(f"\n{'='*50}")
    print(f"EthicPrint Source Checker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Carica tutte le fonti
    res = supabase.table("sources").select("id, url, title, publisher, published_at").execute()
    sources = res.data or []
    print(f"Found {len(sources)} sources to check\n")

    results = {"ok": 0, "broken": 0, "content_missing": 0, "errors": 0}

    async with httpx.AsyncClient() as client:
        for source in sources:
            try:
                checked = await check_source(client, source)

                if checked is None:
                    # Sito blocca bot — skip, non aggiornare
                    results["blocked"] = results.get("blocked", 0) + 1
                    await asyncio.sleep(2)
                    continue

                # Aggiorna Supabase
                supabase.table("sources").update({
                    "broken": checked["broken"],
                    "content_missing": checked["content_missing"],
                    "last_checked": checked["last_checked"],
                }).eq("id", checked["id"]).execute()

                if checked["broken"]:
                    results["broken"] += 1
                elif checked["content_missing"]:
                    results["content_missing"] += 1
                else:
                    results["ok"] += 1

                # Pausa tra richieste per non fare spam
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  ✗ Error on source {source.get('id')}: {e}")
                results["errors"] += 1

    print(f"\n{'='*50}")
    print(f"DONE — ✓ {results['ok']} OK · ✗ {results['broken']} broken · ⚠ {results['content_missing']} content missing · 🚫 {results.get('blocked',0)} blocked · {results['errors']} errors")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    asyncio.run(run_checker())
