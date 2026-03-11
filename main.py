from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os
import json
import httpx
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SUPPORTED_LANGS = ["en", "it", "es", "fr", "de"]
DEFAULT_LANG = "en"

# ─── TIER PUBLISHER ───────────────────────────────────────────────────────────
# Tier 1 = fonti autorevoli internazionali (peso 3)
# Tier 2 = testate nazionali, report ufficiali, dati governativi (peso 2)
# Tier 3 = blog, fonti minori, non verificate (peso 1)

TIER_WEIGHTS = {1: 3, 2: 2, 3: 1}

# Cache publishers from DB (refreshed every hour)
_publishers_cache: dict = {}
_publishers_cache_time: float = 0

def _load_publishers() -> dict:
    """Carica i publisher dal DB e li mette in cache per 1 ora."""
    import time
    global _publishers_cache, _publishers_cache_time
    now = time.time()
    if _publishers_cache and (now - _publishers_cache_time) < 3600:
        return _publishers_cache
    try:
        res = supabase.table("publishers").select("name, tier").eq("active", True).execute()
        cache = {}
        for row in (res.data or []):
            cache[row["name"].lower().strip()] = row["tier"]
        _publishers_cache = cache
        _publishers_cache_time = now
    except Exception as e:
        print(f"Publishers cache load failed: {e}")
    return _publishers_cache

def detect_tier(publisher: str) -> int:
    """Assegna il tier in base al publisher dal DB. Fallback tier 3."""
    if not publisher:
        return 3
    p = publisher.lower().strip()
    publishers = _load_publishers()
    # Match esatto o parziale (es. "The Guardian" dentro "The Guardian - International")
    for name, tier in publishers.items():
        if name in p or p in name:
            return tier
    return 3

def weighted_confidence(sources: list) -> dict:
    """
    Calcola confidence pesata per categoria.
    Peso: tier1=3, tier2=2, tier3=1
    Soglie score pesato:
      high   → ≥ 6  (es. 2× tier1, o 1× tier1 + 1× tier2 + 1× tier3, ...)
      medium → ≥ 3  (es. 1× tier1, o 3× tier3)
      low    → ≥ 1
      none   → 0
    Una singola fonte Tier 1 = medium (peso 3 ≥ 3).
    Due fonti Tier 1 = high (peso 6 ≥ 6).
    """
    # raggruppa per categoria
    grouped = {}
    for s in sources:
        key = s.get("category_key")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(s)

    result = {}
    for cat in ["armi", "ambiente", "diritti", "fisco"]:
        cat_sources = grouped.get(cat, [])
        count = len(cat_sources)
        # score pesato
        weighted = sum(TIER_WEIGHTS.get(s.get("tier", 3), 1) for s in cat_sources)
        # breakdown per tier
        t1 = sum(1 for s in cat_sources if s.get("tier") == 1)
        t2 = sum(1 for s in cat_sources if s.get("tier") == 2)
        t3 = sum(1 for s in cat_sources if s.get("tier", 3) == 3)

        if weighted >= 6:
            level = "high"
        elif weighted >= 3:
            level = "medium"
        elif weighted >= 1:
            level = "low"
        else:
            level = "none"

        result[cat] = {
            "level": level,
            "label_en": {"high": "High confidence", "medium": "Medium confidence",
                         "low": "Low confidence", "none": "No sources yet"}[level],
            "label_it": {"high": "Alta affidabilità", "medium": "Attendibilità media",
                         "low": "Bassa affidabilità", "none": "Nessuna fonte"}[level],
            "count": count,
            "weighted_score": weighted,
            "tier1": t1, "tier2": t2, "tier3": t3,
        }
    return result

app = FastAPI(
    title="EthicPrint API",
    description="API for ethical brand scoring — ethicprint.org",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ethicprint.org", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── UTILS ────────────────────────────────────────────────────────────────────

def apply_translation(brand: dict, translation: dict) -> dict:
    """Sovrascrive note e alternatives del brand con la traduzione richiesta."""
    if not translation:
        return brand
    if translation.get("note_armi"):
        brand["note_armi"] = translation["note_armi"]
    if translation.get("note_ambiente"):
        brand["note_ambiente"] = translation["note_ambiente"]
    if translation.get("note_diritti"):
        brand["note_diritti"] = translation["note_diritti"]
    if translation.get("note_fisco"):
        brand["note_fisco"] = translation["note_fisco"]
    return brand


def format_brand(brand: dict, sources: list = [], translation: dict = None, lang: str = "en") -> dict:
    """Trasforma una riga del DB nel formato usato dal frontend."""
    if translation:
        brand = apply_translation(dict(brand), translation)

    sector = brand.get("sectors") or {}
    grouped_sources = {}
    for s in sources:
        key = s["category_key"]
        if key not in grouped_sources:
            grouped_sources[key] = []
        grouped_sources[key].append({
            "url": s["url"],
            "title": s["title"],
            "publisher": s["publisher"],
            "published_at": s["published_at"],
            "tier": s.get("tier", 3),
        })

    sector_label = sector.get("label_en", "") if lang == "en" and sector.get("label_en") else sector.get("label", "")

    return {
        "id": brand["id"],
        "name": brand["name"],
        "sector": sector_label,
        "sector_key": sector.get("key", ""),
        "sector_icon": sector.get("icon", ""),
        "logo": brand["logo"],
        "parent": brand["parent"],
        "scores": {
            "armi": brand["score_armi"],
            "ambiente": brand["score_ambiente"],
            "diritti": brand["score_diritti"],
            "fisco": brand["score_fisco"],
        },
        "notes": {
            "armi": brand["note_armi"],
            "ambiente": brand["note_ambiente"],
            "diritti": brand["note_diritti"],
            "fisco": brand["note_fisco"],
        },
        "sources": grouped_sources,
        "alternatives": [],  # populated by smart_alternatives()
        "last_updated": brand["last_updated"],
    }


def get_translation(brand_id: int, lang: str) -> dict | None:
    """Recupera la traduzione dal DB. Ritorna None se non esiste."""
    if lang == DEFAULT_LANG:
        return None
    try:
        res = supabase.table("brand_translations")\
            .select("*")\
            .eq("brand_id", brand_id)\
            .eq("lang", lang)\
            .limit(1)\
            .execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        print(f"get_translation error brand_id={brand_id} lang={lang}: {e}")
        return None


async def generate_and_save_translation(brand_id: int, brand: dict, lang: str):
    """Chiama Claude API per generare una traduzione e la salva in brand_translations."""
    if not ANTHROPIC_KEY:
        return

    lang_names = {"it": "Italian", "es": "Spanish", "fr": "French", "de": "German"}
    lang_name = lang_names.get(lang, lang)

    prompt = f"""Translate the following ethical brand assessment notes from English to {lang_name}.
Return ONLY a valid JSON object with these exact keys: note_armi, note_ambiente, note_diritti, note_fisco.
Keep the tone factual and neutral. Do not add or remove information.

Brand: {brand["name"]}

note_armi: {brand["note_armi"]}
note_ambiente: {brand["note_ambiente"]}
note_diritti: {brand["note_diritti"]}
note_fisco: {brand["note_fisco"]}
"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30.0
            )
            data = response.json()
            text = data["content"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            translated = json.loads(text.strip())

        supabase.table("brand_translations").upsert({
            "brand_id": brand_id,
            "lang": lang,
            "note_armi": translated.get("note_armi"),
            "note_ambiente": translated.get("note_ambiente"),
            "note_diritti": translated.get("note_diritti"),
            "note_fisco": translated.get("note_fisco"),
        }, on_conflict="brand_id,lang").execute()

    except Exception as e:
        print(f"Translation error for brand {brand_id} lang {lang}: {e}")


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "EthicPrint API v2.0.0 — ethicprint.org"}


@app.get("/brands")
def get_brands(
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    lang: Optional[str] = Query("en"),
):
    """Ritorna tutti i brand. Supporta ?lang=it per le traduzioni."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    query = supabase.table("brands").select("*, sectors(key, label, label_en, icon)")

    if sector:
        sector_res = supabase.table("sectors").select("id").eq("key", sector).single().execute()
        if not sector_res.data:
            raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
        query = query.eq("sector_id", sector_res.data["id"])

    res = query.order("name").execute()
    brands = res.data or []

    if search:
        search_lower = search.lower()
        brands = [b for b in brands if search_lower in b["name"].lower()]

    if lang != DEFAULT_LANG:
        translations_res = supabase.table("brand_translations")\
            .select("*")\
            .eq("lang", lang)\
            .execute()
        translations = {t["brand_id"]: t for t in (translations_res.data or [])}
        return [format_brand(b, translation=translations.get(b["id"]), lang=lang) for b in brands]

    return [format_brand(b, lang=lang) for b in brands]



def smart_alternatives(brand_id: int, sector_id: int, lang: str, top_n: int = 3) -> list:
    """Ritorna i top N brand dello stesso settore per score, escluso il brand stesso."""
    res = supabase.table("brands")        .select("id, name, logo, score_armi, score_ambiente, score_diritti, score_fisco, sectors(key, label, label_en, icon)")        .eq("sector_id", sector_id)        .neq("id", brand_id)        .execute()

    brands = res.data or []

    def total_score(b):
        return (b["score_armi"] + b["score_ambiente"] + b["score_diritti"] + b["score_fisco"]) / 4

    # Calcola score del brand corrente per confronto
    current_res = supabase.table("brands")        .select("score_armi, score_ambiente, score_diritti, score_fisco")        .eq("id", brand_id).limit(1).execute()
    current_score = 0
    if current_res.data:
        c = current_res.data[0]
        current_score = (c["score_armi"] + c["score_ambiente"] + c["score_diritti"] + c["score_fisco"]) / 4

    # Ritorna solo brand con score più alto del brand corrente
    better = [b for b in brands if total_score(b) > current_score]
    brands_sorted = sorted(better, key=total_score, reverse=True)[:top_n]

    result = []
    for b in brands_sorted:
        sector = b.get("sectors") or {}
        sector_label = sector.get("label_en", "") if lang == "en" and sector.get("label_en") else sector.get("label", "")
        result.append({
            "id": b["id"],
            "name": b["name"],
            "logo": b["logo"],
            "score": round(total_score(b)),
            "sector": sector_label,
        })
    return result

@app.get("/brands/{brand_id}")
async def get_brand(
    brand_id: int,
    lang: Optional[str] = Query("en"),
    background_tasks: BackgroundTasks = None,
):
    """Ritorna un singolo brand nella lingua richiesta.
    Se la traduzione non esiste, la genera in background e ritorna l'inglese."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    brand_res = supabase.table("brands")\
        .select("*, sectors(key, label, label_en, icon)")\
        .eq("id", brand_id)\
        .single()\
        .execute()

    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    sources_res = supabase.table("sources")\
        .select("id, url, title, publisher, published_at, category_key, tier")\
        .eq("brand_id", brand_id)\
        .neq("broken", True)\
        .neq("content_missing", True)\
        .order("category_key")\
        .execute()

    translation = None
    if lang != DEFAULT_LANG:
        translation = get_translation(brand_id, lang)
        if not translation and background_tasks and ANTHROPIC_KEY:
            background_tasks.add_task(
                generate_and_save_translation,
                brand_id,
                brand_res.data,
                lang
            )

    formatted = format_brand(brand_res.data, sources_res.data or [], translation, lang=lang)

    # Confidence pesata per tier — tier1=3pts, tier2=2pts, tier3=1pt
    formatted["confidence"] = weighted_confidence(sources_res.data or [])

    sector_id = brand_res.data.get("sector_id")
    if sector_id:
        formatted["alternatives"] = smart_alternatives(brand_id, sector_id, lang)
    return formatted


@app.get("/sectors")
def get_sectors():
    res = supabase.table("sectors")\
        .select("*")\
        .eq("active", True)\
        .order("sort_order")\
        .execute()
    return res.data or []


@app.get("/categories")
def get_categories():
    res = supabase.table("categories")\
        .select("*")\
        .eq("active", True)\
        .order("sort_order")\
        .execute()
    return res.data or []


@app.get("/brands/{brand_id}/sources")
def get_brand_sources(brand_id: int):
    brand_res = supabase.table("brands").select("id").eq("id", brand_id).single().execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    res = supabase.table("sources")\
        .select("*")\
        .eq("brand_id", brand_id)\
        .neq("broken", True)\
        .neq("content_missing", True)\
        .order("category_key")\
        .execute()

    grouped = {}
    for s in (res.data or []):
        key = s["category_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append({
            "id": s["id"],
            "url": s["url"],
            "title": s["title"],
            "publisher": s["publisher"],
            "published_at": s["published_at"],
        })

    return grouped


@app.get("/langs")
def get_langs():
    """Ritorna le lingue supportate."""
    return {
        "default": DEFAULT_LANG,
        "supported": SUPPORTED_LANGS,
        "labels": {"en": "English", "it": "Italiano", "es": "Español", "fr": "Français", "de": "Deutsch"}
    }


@app.post("/suggest")
def suggest_brand(payload: dict):
    required = ["name", "sector", "reason"]
    for field in required:
        if field not in payload or not payload[field]:
            raise HTTPException(status_code=422, detail=f"Field '{field}' required")
    return {
        "message": "Thanks for the suggestion! It will be reviewed by Marco.",
        "brand": payload.get("name")
    }


@app.get("/publishers")
def get_publishers():
    """Ritorna tutti i publisher trusted, divisi per tier."""
    res = supabase.table("publishers")        .select("id, name, url, tier, topic")        .eq("active", True)        .order("tier")        .order("name")        .execute()
    data = res.data or []
    return {
        "total": len(data),
        "tier1": [p for p in data if p["tier"] == 1],
        "tier2": [p for p in data if p["tier"] == 2],
        "tier3": [p for p in data if p["tier"] == 3],
    }


@app.get("/sources/public")
def get_public_sources():
    """Ritorna tutte le fonti valide con brand e tier, per la pagina pubblica."""
    res = supabase.table("sources")\
        .select("id, url, title, publisher, published_at, category_key, tier, brand_id, brands(name)")\
        .neq("broken", True)\
        .neq("content_missing", True)\
        .order("tier")\
        .execute()
    sources = res.data or []
    # Arricchisci con tier auto-detect se tier è null o mancante
    for s in sources:
        if not s.get("tier"):
            s["tier"] = detect_tier(s.get("publisher", ""))
    total = len(sources)
    by_tier = {1: [], 2: [], 3: []}
    for s in sources:
        t = s.get("tier", 3)
        by_tier[t if t in [1,2,3] else 3].append(s)
    return {
        "total": total,
        "tier1": by_tier[1],
        "tier2": by_tier[2],
        "tier3": by_tier[3],
    }


@app.get("/sources/issues")
def get_source_issues():
    """Ritorna tutte le fonti con problemi (broken o content_missing) per revisione."""
    res = supabase.table("sources")\
        .select("id, url, title, publisher, published_at, broken, content_missing, last_checked, brand_id")\
        .or_("broken.eq.true,content_missing.eq.true")\
        .order("last_checked", desc=True)\
        .execute()
    return {
        "count": len(res.data or []),
        "issues": res.data or []
    }


@app.get("/source-proposals")
def get_source_proposals(status: str = "pending"):
    """Ritorna le proposte di fonti filtrate per status (pending/approved/rejected)."""
    res = supabase.table("source_proposals")\
        .select("*, brands(name)")\
        .eq("status", status)\
        .order("created_at", desc=True)\
        .execute()
    return {"count": len(res.data or []), "proposals": res.data or []}


async def analyze_source_for_score(source_id: int, brand_id: int, category_key: str, url: str, title: str, summary: str):
    """
    Dopo l'approvazione di una fonte, Claude legge la pagina e suggerisce
    una modifica al punteggio della categoria. Salva in score_proposals.
    MAI aggiornamento automatico — richiede approvazione manuale.
    """
    if not ANTHROPIC_KEY:
        return

    # Recupera punteggio attuale del brand
    brand_res = supabase.table("brands")        .select(f"score_{category_key}, name")        .eq("id", brand_id).single().execute()
    if not brand_res.data:
        return

    current_score = brand_res.data.get(f"score_{category_key}", 50)
    brand_name = brand_res.data.get("name", "")

    # Fetch contenuto pagina
    page_content = ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            if r.status_code == 200:
                page_content = r.text[:6000]
    except Exception:
        pass

    cat_descriptions = {
        "armi": "arms, weapons, military contracts, conflicts",
        "ambiente": "environment, CO2 emissions, climate, sustainability",
        "diritti": "human rights, labor rights, workers conditions",
        "fisco": "tax avoidance, tax haven, fiscal transparency",
    }

    prompt = f"""You are an ethical analyst for EthicPrint, scoring brands on ethical dimensions.

Brand: {brand_name}
Category: {category_key} ({cat_descriptions.get(category_key, category_key)})
Current score: {current_score}/100
Source title: {title}
Source summary: {summary}
Source content (truncated):
{page_content or "(page not accessible)"}

Based on this source, should the score for {brand_name} on {category_key} change?
Consider: higher score = more ethical. The source may reveal positive or negative behavior.

Reply ONLY with JSON:
{{
  "proposed_score": <integer 0-100>,
  "motivation": "<2-3 sentences explaining why the score should change, or stay the same>",
  "direction": "increase" | "decrease" | "unchanged"
}}"""

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            result = json.loads(text)
            proposed_score = max(0, min(100, int(result.get("proposed_score", current_score))))
            motivation = result.get("motivation", "")

            supabase.table("score_proposals").insert({
                "brand_id": brand_id,
                "category_key": category_key,
                "source_id": source_id,
                "current_score": current_score,
                "proposed_score": proposed_score,
                "motivation": motivation,
                "status": "pending",
            }).execute()
            print(f"Score proposal saved: {brand_name} / {category_key} {current_score}→{proposed_score}")
    except Exception as e:
        print(f"Score analysis failed: {e}")


@app.post("/source-proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: int, background_tasks: BackgroundTasks):
    """Approva una proposta: la inserisce in sources, avvia analisi score."""
    prop_res = supabase.table("source_proposals").select("*").eq("id", proposal_id).single().execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = prop_res.data

    # Inserisci in sources con tier auto-rilevato dal publisher
    new_source = supabase.table("sources").insert({
        "brand_id": p["brand_id"],
        "category_key": p["category_key"],
        "url": p["url"],
        "title": p["title"],
        "publisher": p["publisher"],
        "broken": False,
        "content_missing": False,
        "tier": detect_tier(p.get("publisher", "")),
    }).execute()

    source_id = new_source.data[0]["id"] if new_source.data else None

    # Marca proposta come approvata
    supabase.table("source_proposals").update({"status": "approved"}).eq("id", proposal_id).execute()

    # Se era un sostituto, elimina la fonte originale rotta
    if p.get("replaces_id"):
        supabase.table("sources").delete().eq("id", p["replaces_id"]).execute()

    # Analisi score in background — non blocca la risposta
    if source_id:
        background_tasks.add_task(
            analyze_source_for_score,
            source_id=source_id,
            brand_id=p["brand_id"],
            category_key=p["category_key"],
            url=p["url"],
            title=p.get("title", ""),
            summary=p.get("summary", ""),
        )

    return {"message": "Proposal approved. Score analysis started in background."}


@app.post("/source-proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int):
    """Rifiuta una proposta."""
    supabase.table("source_proposals").update({"status": "rejected"}).eq("id", proposal_id).execute()
    return {"message": "Proposal rejected"}


@app.get("/score-proposals")
def get_score_proposals(status: str = "pending"):
    """Ritorna le proposte di modifica punteggio filtrate per status."""
    res = supabase.table("score_proposals")        .select("*, brands(name), sources(url, title, publisher)")        .eq("status", status)        .order("created_at", desc=True)        .execute()
    return {"count": len(res.data or []), "proposals": res.data or []}


@app.post("/score-proposals/{proposal_id}/approve")
def approve_score_proposal(proposal_id: int):
    """Approva una proposta di score: aggiorna il punteggio nel brand."""
    prop_res = supabase.table("score_proposals").select("*").eq("id", proposal_id).single().execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = prop_res.data

    col = f"score_{p['category_key']}"
    supabase.table("brands").update({
        col: p["proposed_score"],
        "last_updated": "now()"
    }).eq("id", p["brand_id"]).execute()

    supabase.table("score_proposals").update({"status": "approved"}).eq("id", proposal_id).execute()
    return {"message": f"Score updated: {p['category_key']} → {p['proposed_score']}"}


@app.post("/score-proposals/{proposal_id}/reject")
def reject_score_proposal(proposal_id: int):
    """Rifiuta una proposta di score."""
    supabase.table("score_proposals").update({"status": "rejected"}).eq("id", proposal_id).execute()
    return {"message": "Score proposal rejected"}
