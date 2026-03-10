from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
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
        .select("*")\
        .eq("brand_id", brand_id)\
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
