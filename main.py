from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
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

app = FastAPI(title="EthicPrint API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── SCORING V2 CONSTANTS ────────────────────────────────────────────────────
TIER_VALUES = {
    1: {"positive": 20, "prev_positive": 10, "prev_negative": -10, "negative": -20},
    2: {"positive": 10, "prev_positive":  5, "prev_negative":  -5, "negative": -10},
    3: {"positive":  2, "prev_positive":  1, "prev_negative":  -1, "negative":  -2},
}
SCORE_LABELS = {
    "positive":      {"en": "Positive evidence",       "it": "Evidenza positiva"},
    "prev_positive": {"en": "Predominantly positive",  "it": "Prevalentemente positiva"},
    "prev_negative": {"en": "Predominantly negative",  "it": "Prevalentemente negativa"},
    "negative":      {"en": "Negative evidence",       "it": "Evidenza negativa"},
}

FRESHNESS_MONTHS = 18
SCORE_RANGE = 400
CATS = ["armi", "ambiente", "diritti", "fisco"]

VERDICTS = [
    (200,  400, "Deeply Ethical",        "Profondamente Etico",   "🌿"),
    ( 50,  199, "Fairly Ethical",         "Abbastanza Etico",      "✅"),
    (-49,   49, "Partially Ethical",      "Parzialmente Etico",    "⚖️"),
    (-199, -50, "Scarcely Ethical",       "Scarsamente Etico",     "⚠️"),
    (-400,-200, "Ethically Compromised",  "Eticamente Inadeguato", "🚫"),
]

TIER_WEIGHTS = {1: 3, 2: 2, 3: 1}
MIN_SOURCES_PER_CAT = 2

# ─── PUBLISHER CACHE ─────────────────────────────────────────────────────────
_publishers_cache: dict = {}
_publishers_cache_time: float = 0

def _load_publishers() -> dict:
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
    if not publisher:
        return 3
    p = publisher.lower().strip()
    publishers = _load_publishers()
    for name, tier in publishers.items():
        if name in p or p in name:
            return tier
    return 3


# ─── SCORING LOGIC ───────────────────────────────────────────────────────────
def compute_criterion_score(css_rows: list) -> dict:
    published = [r for r in css_rows if r.get("status") == "published"]
    t1 = [r for r in published if r.get("tier") == 1]
    t2 = [r for r in published if r.get("tier") == 2]
    t3 = [r for r in published if r.get("tier", 3) == 3]

    def avg(rows): return sum(r["value"] for r in rows) / len(rows)

    if t1:
        score = avg(t1)
        tier_used = 1
        criteria_met = True
    elif len(t2) >= 2:
        score = avg(t2)
        tier_used = 2
        criteria_met = True
    elif len(t2) == 1 and len(t3) >= 3:
        t3_avg = avg(t3)
        score = t2[0]["value"] + t3_avg
        tier_used = 2
        criteria_met = True
    else:
        score = None
        tier_used = None
        criteria_met = False

    if score is not None:
        score = max(-20, min(20, round(score)))

    return {
        "score": score,
        "criteria_met": criteria_met,
        "tier_used": tier_used,
        "t1": len(t1), "t2": len(t2), "t3": len(t3),
    }


def compute_brand_score_v2(brand_id: int) -> dict:
    css_res = supabase.table("criterion_source_scores") \
        .select("criterion_id, tier, value, status, scoring_criteria(category_key)") \
        .eq("brand_id", brand_id) \
        .execute()
    all_css = css_res.data or []

    by_criterion = {}
    for row in all_css:
        cid = row["criterion_id"]
        if cid not in by_criterion:
            by_criterion[cid] = []
        by_criterion[cid].append(row)

    total = 0.0
    criteria_published = 0
    criterion_results = {}

    for cid, rows in by_criterion.items():
        result = compute_criterion_score(rows)
        criterion_results[cid] = result
        if result["criteria_met"] and result["score"] is not None:
            total += result["score"]
            criteria_published += 1
            supabase.table("brand_scores").upsert({
                "brand_id": brand_id,
                "criterion_id": cid,
                "computed_score": result["score"],
                "criteria_met": True,
                "status": "published",
                "last_updated": "now()",
            }, on_conflict="brand_id,criterion_id").execute()

    total_rounded = round(total, 1)

    supabase.table("brands").update({
        "total_score_v2": total_rounded,
        "criteria_published": criteria_published,
        "last_updated": "now()",
    }).eq("id", brand_id).execute()

    return {
        "total_score_v2": total_rounded,
        "criteria_published": criteria_published,
        "criterion_results": criterion_results,
    }


def get_verdict(score: float, lang: str = "en") -> dict:
    for low, high, label_en, label_it, emoji in VERDICTS:
        if low <= score <= high:
            return {"label": label_en if lang == "en" else label_it, "emoji": emoji, "band": label_en}
    return {"label": "Unknown", "emoji": "❓", "band": "Unknown"}


def source_confidence_v2(css_rows: list) -> dict:
    from datetime import datetime, timezone, timedelta
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_MONTHS * 30)
    result = {}
    for cat in CATS:
        cat_rows = [r for r in css_rows if
                    (r.get("scoring_criteria") or {}).get("category_key") == cat
                    and r.get("status") == "published"]
        t1 = sum(1 for r in cat_rows if r.get("tier") == 1)
        t2 = sum(1 for r in cat_rows if r.get("tier") == 2)
        t3 = sum(1 for r in cat_rows if r.get("tier", 3) == 3)
        total = len(cat_rows)
        met = t1 >= 1 or t2 >= 2 or (t2 == 1 and t3 >= 3)
        if t1 >= 2 or (t1 == 1 and t2 >= 1):
            level = "high"
        elif t1 == 1 or t2 >= 2:
            level = "medium"
        elif total >= 1:
            level = "low"
        else:
            level = "none"
        result[cat] = {
            "level": level, "criteria_met": met,
            "label_en": {"high": "High confidence", "medium": "Medium confidence",
                         "low": "Low confidence", "none": "No sources yet"}[level],
            "label_it": {"high": "Alta affidabilità", "medium": "Attendibilità media",
                         "low": "Bassa affidabilità", "none": "Nessuna fonte"}[level],
            "count": total, "t1": t1, "t2": t2, "t3": t3,
        }
    return result


def weighted_confidence(sources: list) -> dict:
    from datetime import datetime, timezone, timedelta
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_MONTHS * 30)
    grouped = {}
    for s in sources:
        key = s.get("category_key")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(s)
    result = {}
    for cat in CATS:
        cat_sources = grouped.get(cat, [])
        count = len(cat_sources)
        fresh_count = 0
        for s in cat_sources:
            pub = s.get("published_at")
            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    if pub_dt >= freshness_cutoff:
                        fresh_count += 1
                except Exception:
                    pass
            else:
                fresh_count += 1
        t1 = sum(1 for s in cat_sources if s.get("tier") == 1)
        t2 = sum(1 for s in cat_sources if s.get("tier") == 2)
        t3 = sum(1 for s in cat_sources if s.get("tier", 3) == 3)
        met = t1 >= 1 or t2 >= 2 or (t2 == 1 and t3 >= 3)
        weighted = sum(TIER_WEIGHTS.get(s.get("tier", 3), 1) for s in cat_sources)
        if weighted >= 6:    level = "high"
        elif weighted >= 3:  level = "medium"
        elif weighted >= 1:  level = "low"
        else:                level = "none"
        result[cat] = {
            "level": level, "criteria_met": met,
            "data_status": "ok" if met else ("insufficient" if count == 1 else "none"),
            "fresh_count": fresh_count,
            "label_en": {"high": "High confidence", "medium": "Medium confidence",
                         "low": "Low confidence", "none": "No sources yet"}[level],
            "label_it": {"high": "Alta affidabilità", "medium": "Attendibilità media",
                         "low": "Bassa affidabilità", "none": "Nessuna fonte"}[level],
            "count": count, "weighted_score": weighted,
            "tier1": t1, "tier2": t2, "tier3": t3,
        }
    return result


async def generate_impact_summary(brand_id: int, brand: dict, criterion_scores: list = None) -> dict:
    if not ANTHROPIC_KEY:
        return {}
    import httpx as _httpx
    name = brand.get("name", "")
    sector = (brand.get("sectors") or {}).get("label_en", "")
    total_score = brand.get("total_score_v2")
    criteria_published = brand.get("criteria_published", 0) or 0
    if total_score is None or criteria_published == 0:
        return {}
    verdict = get_verdict(total_score)
    band = verdict["band"]
    notes = {
        "armi":     brand.get("note_armi", "") or "",
        "ambiente": brand.get("note_ambiente", "") or "",
        "diritti":  brand.get("note_diritti", "") or "",
        "fisco":    brand.get("note_fisco", "") or "",
    }
    notes_text = "\n".join([f"- {cat}: {notes[cat]}" for cat in CATS if notes[cat]])
    criteria_text = ""
    if criterion_scores:
        lines = []
        for c in criterion_scores:
            if c.get("criteria_met") and c.get("computed_score") is not None:
                label = (c.get("criterion") or {}).get("label_en", f"criterion {c.get('criterion_id')}")
                score = c.get("computed_score")
                lines.append(f"  - {label}: {'+' if score > 0 else ''}{score}/20")
        if lines:
            criteria_text = "Criteria scores (−20 to +20):\n" + "\n".join(lines)
    prompt = f"""You are writing a concise ethical impact summary for EthicPrint, a brand ethics scoring tool.

Brand: {name}
Sector: {sector}
Overall score: {total_score} out of ±400 → verdict: {band}
Criteria with published scores: {criteria_published}/20

{criteria_text}

{("Notes:\n" + notes_text) if notes_text else ""}

Write TWO short sentences (max 35 words each) that tell a consumer the CONCRETE ethical impact of choosing or avoiding this brand.
Be specific, factual, and direct. No marketing language. Focus on the strongest signal in the data.

Return ONLY valid JSON:
{{"en": "English sentence here.", "it": "Frase italiana qui."}}"""
    try:
        async with _httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            result = __import__("json").loads(text)
            en = result.get("en", "")
            it = result.get("it", "")
            if en and it:
                supabase.table("brands").update({
                    "impact_summary_en": en,
                    "impact_summary_it": it,
                }).eq("id", brand_id).execute()
            return {"en": en, "it": it}
    except Exception as e:
        print(f"generate_impact_summary error: {e}")
        return {}


def format_brand(brand: dict, sources: list = [], translation: dict = None, lang: str = "en") -> dict:
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
    confidence = weighted_confidence(sources)
    total_score_v2 = brand.get("total_score_v2")
    criteria_published = brand.get("criteria_published", 0) or 0
    cat_score_map = {
        "armi":     brand.get("score_armi", 0) or 0,
        "ambiente": brand.get("score_ambiente", 0) or 0,
        "diritti":  brand.get("score_diritti", 0) or 0,
        "fisco":    brand.get("score_fisco", 0) or 0,
    }
    insufficient_data = (total_score_v2 is None and criteria_published == 0)
    return {
        "id": brand["id"],
        "name": brand["name"],
        "sector": sector_label,
        "sector_key": sector.get("key", ""),
        "sector_icon": sector.get("icon", ""),
        "logo": brand["logo"],
        "parent": brand["parent"],
        "scores": cat_score_map,
        "total_score": total_score_v2,
        "criteria_published": criteria_published,
        "insufficient_data": insufficient_data,
        "notes": {
            "armi": brand["note_armi"],
            "ambiente": brand["note_ambiente"],
            "diritti": brand["note_diritti"],
            "fisco": brand["note_fisco"],
        },
        "sources": grouped_sources,
        "confidence": confidence,
        "impact_summary": brand.get(f"impact_summary_{lang}") or brand.get("impact_summary_en") or "",
        "alternatives": [],
        "last_updated": brand["last_updated"],
    }


def apply_translation(brand: dict, translation: dict) -> dict:
    for field in ["note_armi", "note_ambiente", "note_diritti", "note_fisco"]:
        if translation.get(field):
            brand[field] = translation[field]
    return brand


def get_translation(brand_id: int, lang: str) -> dict | None:
    if lang == DEFAULT_LANG:
        return None
    try:
        res = supabase.table("brand_translations") \
            .select("*") \
            .eq("brand_id", brand_id) \
            .eq("lang", lang) \
            .limit(1) \
            .execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        print(f"get_translation error brand_id={brand_id} lang={lang}: {e}")
        return None


async def generate_and_save_translation(brand_id: int, brand: dict, lang: str):
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
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1000,
                      "messages": [{"role": "user", "content": prompt}]},
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
            "brand_id": brand_id, "lang": lang,
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
        translations_res = supabase.table("brand_translations").select("*").eq("lang", lang).execute()
        translations = {t["brand_id"]: t for t in (translations_res.data or [])}
        return [format_brand(b, translation=translations.get(b["id"]), lang=lang) for b in brands]
    return [format_brand(b, lang=lang) for b in brands]


def smart_alternatives(brand_id: int, sector_id: int, lang: str, top_n: int = 3) -> list:
    res = supabase.table("brands") \
        .select("id, name, logo, total_score_v2, criteria_published, sectors(key, label, label_en, icon)") \
        .eq("sector_id", sector_id).neq("id", brand_id).not_.is_("total_score_v2", "null").execute()
    brands = res.data or []
    current_res = supabase.table("brands").select("total_score_v2").eq("id", brand_id).limit(1).execute()
    current_score = None
    if current_res.data:
        current_score = current_res.data[0].get("total_score_v2")
    if current_score is not None:
        better = [b for b in brands if (b.get("total_score_v2") or -400) > current_score]
    else:
        better = brands
    brands_sorted = sorted(better, key=lambda b: b.get("total_score_v2") or -400, reverse=True)[:top_n]
    result = []
    for b in brands_sorted:
        sector = b.get("sectors") or {}
        sector_label = sector.get("label_en", "") if lang == "en" and sector.get("label_en") else sector.get("label", "")
        result.append({
            "id": b["id"], "name": b["name"], "logo": b["logo"],
            "score": b.get("total_score_v2"), "criteria_published": b.get("criteria_published", 0),
            "sector": sector_label,
        })
    return result


@app.get("/brands/{brand_id}")
async def get_brand(
    brand_id: int,
    lang: Optional[str] = Query("en"),
    background_tasks: BackgroundTasks = None,
):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    brand_res = supabase.table("brands").select("*, sectors(key, label, label_en, icon)") \
        .eq("id", brand_id).single().execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")
    sources_res = supabase.table("sources").select("id, url, title, publisher, published_at, category_key, tier") \
        .eq("brand_id", brand_id).neq("broken", True).neq("content_missing", True).order("category_key").execute()
    translation = None
    if lang != DEFAULT_LANG:
        translation = get_translation(brand_id, lang)
        if not translation and background_tasks and ANTHROPIC_KEY:
            background_tasks.add_task(generate_and_save_translation, brand_id, brand_res.data, lang)
    formatted = format_brand(brand_res.data, sources_res.data or [], translation, lang=lang)
    formatted["confidence"] = weighted_confidence(sources_res.data or [])
    if not brand_res.data.get("impact_summary_en") and background_tasks and ANTHROPIC_KEY:
        try:
            css_res = supabase.table("criterion_source_scores") \
                .select("*, scoring_criteria(label_en, category_key)") \
                .eq("brand_id", brand_id).eq("status", "published").execute()
            css_rows = css_res.data or []
            by_crit = {}
            for r in css_rows:
                cid = r["criterion_id"]
                if cid not in by_crit:
                    by_crit[cid] = {"criterion": r.get("scoring_criteria"), "rows": []}
                by_crit[cid]["rows"].append(r)
            criterion_scores = []
            for cid, d in by_crit.items():
                comp = compute_criterion_score(d["rows"])
                criterion_scores.append({
                    "criterion_id": cid, "criterion": d["criterion"],
                    "computed_score": comp["score"], "criteria_met": comp["criteria_met"],
                })
        except Exception:
            criterion_scores = []
        background_tasks.add_task(generate_impact_summary, brand_id, brand_res.data, criterion_scores)
    sector_id = brand_res.data.get("sector_id")
    if sector_id:
        formatted["alternatives"] = smart_alternatives(brand_id, sector_id, lang)
    return formatted


@app.get("/sectors")
def get_sectors():
    res = supabase.table("sectors").select("*").eq("active", True).order("sort_order").execute()
    return res.data or []


@app.get("/categories")
def get_categories():
    res = supabase.table("categories").select("*").eq("active", True).order("sort_order").execute()
    return res.data or []


# ─── SOURCES ─────────────────────────────────────────────────────────────────

@app.get("/brands/{brand_id}/sources")
def get_brand_sources(brand_id: int):
    """
    Ritorna tutte le fonti del brand come array flat.
    Include esclusioni per criterio e proposal_id per ogni fonte.
    """
    brand_res = supabase.table("brands").select("id").eq("id", brand_id).single().execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    res = supabase.table("sources") \
        .select("id, url, title, publisher, published_at, category_key, tier") \
        .eq("brand_id", brand_id) \
        .neq("broken", True) \
        .neq("content_missing", True) \
        .order("category_key") \
        .execute()

    # Carica esclusioni per questo brand
    excl_res = supabase.table("source_criterion_exclusions") \
        .select("source_id, criterion_id") \
        .eq("brand_id", brand_id) \
        .execute()
    excl_map: dict = {}
    for e in (excl_res.data or []):
        sid = e["source_id"]
        if sid not in excl_map:
            excl_map[sid] = []
        excl_map[sid].append(e["criterion_id"])

    # Carica proposal_id per ogni fonte (join via URL + brand_id)
    props_res = supabase.table("source_proposals") \
        .select("id, url") \
        .eq("brand_id", brand_id) \
        .eq("status", "approved") \
        .execute()
    proposal_by_url = {p["url"]: p["id"] for p in (props_res.data or [])}

    sources = []
    for s in (res.data or []):
        sources.append({
            "id": s["id"],
            "url": s["url"],
            "title": s["title"],
            "publisher": s["publisher"],
            "published_at": s["published_at"],
            "category_key": s["category_key"],
            "tier": s.get("tier", 3),
            "excluded_from_criteria": excl_map.get(s["id"], []),
            "proposal_id": proposal_by_url.get(s["url"]),
        })

    return {"sources": sources}


@app.get("/langs")
def get_langs():
    return {
        "default": DEFAULT_LANG,
        "supported": SUPPORTED_LANGS,
        "labels": {"en": "English", "it": "Italiano", "es": "Español", "fr": "Français", "de": "Deutsch"}
    }


@app.get("/publishers")
def get_publishers():
    res = supabase.table("publishers").select("id, name, url, tier, topic") \
        .eq("active", True).order("tier").order("name").execute()
    data = res.data or []
    return {
        "total": len(data),
        "tier1": [p for p in data if p["tier"] == 1],
        "tier2": [p for p in data if p["tier"] == 2],
        "tier3": [p for p in data if p["tier"] == 3],
    }


@app.get("/costs/brave-count")
def get_brave_count():
    now = __import__("datetime").datetime.now()
    month_key = now.strftime("%Y-%m")
    try:
        res = supabase.table("brave_usage").select("*").eq("month", month_key).limit(1).execute()
        if res.data:
            row = res.data[0]
            return {
                "month": row.get("month", month_key),
                "finder": row.get("finder_calls", 0),
                "checker": row.get("checker_calls", 0),
                "month_total": (row.get("finder_calls", 0) + row.get("checker_calls", 0)),
            }
        return {"month": month_key, "finder": 0, "checker": 0, "month_total": 0}
    except Exception as e:
        return {"month": month_key, "finder": 0, "checker": 0, "month_total": 0, "error": str(e)}


@app.get("/sources/public")
def get_public_sources():
    res = supabase.table("sources") \
        .select("id, url, title, publisher, published_at, category_key, tier, brand_id, brands(name)") \
        .neq("broken", True).neq("content_missing", True).order("tier").execute()
    sources = res.data or []
    for s in sources:
        if not s.get("tier"):
            s["tier"] = detect_tier(s.get("publisher", ""))
    total = len(sources)
    by_tier = {1: [], 2: [], 3: []}
    for s in sources:
        t = s.get("tier", 3)
        by_tier[t if t in [1, 2, 3] else 3].append(s)
    return {"total": total, "tier1": by_tier[1], "tier2": by_tier[2], "tier3": by_tier[3]}


@app.get("/sources/issues")
def get_source_issues():
    res = supabase.table("sources") \
        .select("id, url, title, publisher, published_at, broken, content_missing, last_checked, brand_id, category_key") \
        .or_("broken.eq.true,content_missing.eq.true") \
        .order("last_checked", desc=True) \
        .execute()
    return {"count": len(res.data or []), "issues": res.data or []}


# ─── SOURCE EXCLUSIONS ───────────────────────────────────────────────────────

class ExclusionIn(BaseModel):
    brand_id: int
    criterion_id: int

@app.post("/sources/{source_id}/exclude-criterion")
def exclude_source_from_criterion(source_id: int, data: ExclusionIn):
    """Esclude una fonte da un criterio specifico senza rimuoverla dalle altre."""
    try:
        supabase.table("source_criterion_exclusions").upsert({
            "brand_id": data.brand_id,
            "source_id": source_id,
            "criterion_id": data.criterion_id,
        }, on_conflict="brand_id,source_id,criterion_id").execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sources/{source_id}/exclude-criterion/{criterion_id}")
def remove_exclusion(source_id: int, criterion_id: int, brand_id: int = Query(...)):
    """Rimuove l'esclusione di una fonte da un criterio."""
    try:
        supabase.table("source_criterion_exclusions") \
            .delete() \
            .eq("source_id", source_id) \
            .eq("criterion_id", criterion_id) \
            .eq("brand_id", brand_id) \
            .execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── SOURCE PROPOSALS ────────────────────────────────────────────────────────

@app.get("/source-proposals")
def get_source_proposals(status: str = "pending"):
    res = supabase.table("source_proposals") \
        .select("*, brands(name)") \
        .eq("status", status) \
        .order("created_at", desc=True) \
        .execute()
    return {"count": len(res.data or []), "proposals": res.data or []}


@app.patch("/source-proposals/{proposal_id}/revert")
def revert_proposal_to_pending(proposal_id: int):
    """
    Riporta una proposta approved o rejected a stato pending.
    Se era approved, rimuove anche la fonte da sources.
    """
    prop_res = supabase.table("source_proposals").select("*").eq("id", proposal_id).single().execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = prop_res.data

    if p["status"] == "approved":
        # Rimuovi la fonte da sources se esiste (cerca per URL e brand_id)
        src_res = supabase.table("sources") \
            .select("id") \
            .eq("brand_id", p["brand_id"]) \
            .eq("url", p["url"]) \
            .execute()
        if src_res.data:
            source_id = src_res.data[0]["id"]
            # Rimuovi eventuali criterion_source_scores associati
            supabase.table("criterion_source_scores") \
                .delete() \
                .eq("source_id", source_id) \
                .execute()
            # Rimuovi esclusioni
            supabase.table("source_criterion_exclusions") \
                .delete() \
                .eq("source_id", source_id) \
                .execute()
            # Rimuovi la fonte
            supabase.table("sources").delete().eq("id", source_id).execute()
            # Ricalcola punteggio brand
            try:
                compute_brand_score_v2(p["brand_id"])
            except Exception:
                pass

    supabase.table("source_proposals").update({"status": "pending"}).eq("id", proposal_id).execute()
    return {"ok": True, "message": "Proposal reverted to pending"}


class ApproveProposalBody(BaseModel):
    confirmed_judgment: Optional[str] = None

JUDGMENT_VALUES = {
    "Positive":                20,
    "Predominantly positive":  10,
    "Predominantly negative": -10,
    "Negative":               -20,
}
JUDGMENT_LABELS_IT = {
    "Positive":                "Positivo",
    "Predominantly positive":  "Prevalentemente positivo",
    "Predominantly negative":  "Prevalentemente negativo",
    "Negative":                "Negativo",
}

@app.post("/source-proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    background_tasks: BackgroundTasks,
    body: Optional[ApproveProposalBody] = None,
):
    prop_res = supabase.table("source_proposals").select("*").eq("id", proposal_id).single().execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = prop_res.data

    # Usa il tier rilevato dal publisher (fonte di verità)
    tier = detect_tier(p.get("publisher", ""))

    # Inserisci in sources
    new_source = supabase.table("sources").insert({
        "brand_id": p["brand_id"],
        "category_key": p["category_key"],
        "url": p["url"],
        "title": p["title"],
        "publisher": p["publisher"],
        "broken": False,
        "content_missing": False,
        "tier": tier,
    }).execute()
    source_id = new_source.data[0]["id"] if new_source.data else None

    # Marca proposta come approvata, salva tier rilevato
    supabase.table("source_proposals").update({
        "status": "approved",
        "ai_tier": tier,
    }).eq("id", proposal_id).execute()

    # Se era un sostituto, elimina la fonte originale rotta
    if p.get("replaces_id"):
        supabase.table("sources").delete().eq("id", p["replaces_id"]).execute()

    # Pre-popola criterion_source_scores se c'è un giudizio AI
    judgment = (body.confirmed_judgment if body and body.confirmed_judgment else None) or p.get("ai_judgment")
    if source_id and judgment and judgment in JUDGMENT_VALUES:
        tier_values = {
            1: {20: 20, 10: 10, -10: -10, -20: -20},
            2: {20: 10, 10: 5,  -10: -5,  -20: -10},
            3: {20: 2,  10: 1,  -10: -1,  -20: -2},
        }
        base_val = JUDGMENT_VALUES[judgment]
        value = tier_values.get(tier, tier_values[2]).get(base_val, base_val)

        criterion_code = p.get("ai_criterion", "")
        crit_res = None
        if criterion_code:
            crit_res = supabase.table("scoring_criteria").select("id").eq("code", criterion_code).limit(1).execute()
        if not crit_res or not crit_res.data:
            crit_res = supabase.table("scoring_criteria").select("id") \
                .eq("category_key", p["category_key"]).eq("active", True) \
                .order("sort_order").limit(1).execute()

        if crit_res and crit_res.data:
            criterion_id = crit_res.data[0]["id"]
            label_it = JUDGMENT_LABELS_IT.get(judgment, judgment)
            try:
                supabase.table("criterion_source_scores").upsert({
                    "brand_id": p["brand_id"],
                    "criterion_id": criterion_id,
                    "source_id": source_id,
                    "tier": tier,
                    "value": value,
                    "label_en": judgment,
                    "label_it": label_it,
                    "notes": p.get("ai_rationale", ""),
                    "status": "draft",
                }, on_conflict="brand_id,criterion_id,source_id").execute()
                background_tasks.add_task(compute_brand_score_v2, p["brand_id"])
            except Exception as e:
                print(f"criterion_source_scores upsert failed: {e}")

    return {"message": "Proposal approved.", "tier": tier, "judgment_saved": bool(judgment and judgment in JUDGMENT_VALUES)}


@app.post("/source-proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int):
    supabase.table("source_proposals").update({"status": "rejected"}).eq("id", proposal_id).execute()
    return {"message": "Proposal rejected"}


# ─── SCORE PROPOSALS ─────────────────────────────────────────────────────────

@app.get("/score-proposals")
def get_score_proposals(status: str = "pending"):
    res = supabase.table("score_proposals") \
        .select("*, brands(name), sources(url, title, publisher), scoring_criteria(label_en, label_it, code)") \
        .eq("status", status).order("created_at", desc=True).execute()
    return {"count": len(res.data or []), "proposals": res.data or []}


@app.post("/score-proposals/{proposal_id}/approve")
def approve_score_proposal(proposal_id: int):
    prop_res = supabase.table("score_proposals").select("*").eq("id", proposal_id).single().execute()
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = prop_res.data
    criterion_id = p.get("criterion_id")
    if not criterion_id:
        raise HTTPException(status_code=400, detail="Proposal has no criterion_id")

    supabase.table("brand_scores").upsert({
        "brand_id": p["brand_id"],
        "criterion_id": criterion_id,
        "score": p["proposed_score"],
        "label_en": p.get("proposed_label_en", ""),
        "label_it": p.get("proposed_label_it", ""),
        "notes": p.get("motivation", ""),
        "source_ids": [p["source_id"]] if p.get("source_id") else [],
        "status": "published",
        "last_updated": "now()",
    }, on_conflict="brand_id,criterion_id").execute()

    criteria_res = supabase.table("scoring_criteria").select("id") \
        .eq("category_key", p["category_key"]).eq("active", True).execute()
    criterion_ids = [c["id"] for c in (criteria_res.data or [])]
    scores_res = supabase.table("brand_scores").select("score") \
        .eq("brand_id", p["brand_id"]).eq("status", "published").in_("criterion_id", criterion_ids).execute()
    scores = [row["score"] for row in (scores_res.data or [])]
    if scores:
        avg = sum(scores) / len(scores)
        category_score = round((avg - 1) / 4 * 25)
    else:
        category_score = 13

    col = f"score_{p['category_key']}"
    supabase.table("brands").update({col: category_score, "last_updated": "now()"}).eq("id", p["brand_id"]).execute()
    supabase.table("score_proposals").update({"status": "approved"}).eq("id", proposal_id).execute()
    return {"message": "Score updated", "category": p["category_key"], "category_score": category_score}


@app.post("/score-proposals/{proposal_id}/reject")
def reject_score_proposal(proposal_id: int):
    supabase.table("score_proposals").update({"status": "rejected"}).eq("id", proposal_id).execute()
    return {"message": "Score proposal rejected"}


# ─── SCORING CRITERIA ────────────────────────────────────────────────────────

@app.get("/scoring-criteria")
def get_scoring_criteria():
    res = supabase.table("scoring_criteria").select("*").eq("active", True) \
        .order("category_key").order("sort_order").execute()
    data = res.data or []
    # Ritorna sia formato grouped che lista flat con .criteria per compatibilità
    grouped = {}
    for c in data:
        key = c["category_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)
    return {"criteria": data, "grouped": grouped}


@app.get("/brands/{brand_id}/scores")
def get_brand_scores(brand_id: int, lang: Optional[str] = Query("en")):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    criteria_res = supabase.table("scoring_criteria").select("*").eq("active", True) \
        .order("category_key").order("sort_order").execute()
    all_criteria = criteria_res.data or []
    scores_res = supabase.table("brand_scores").select("*").eq("brand_id", brand_id).eq("status", "published").execute()
    scores_by_criterion = {row["criterion_id"]: row for row in (scores_res.data or [])}
    result = {}
    for c in all_criteria:
        key = c["category_key"]
        if key not in result:
            result[key] = []
        s = scores_by_criterion.get(c["id"])
        label_key = f"label_{lang}" if lang != "en" else "label_en"
        result[key].append({
            "criterion_id": c["id"],
            "code": c["code"],
            "label": c[label_key] if label_key in c else c["label_en"],
            "score": s["score"] if s else 3,
            "label_score": (s[f"label_{lang}"] if s and lang != "en" and s.get(f"label_{lang}") else
                           s["label_en"] if s else SCORE_LABELS[3]["en"]),
            "notes": s["notes"] if s else None,
            "last_updated": s["last_updated"] if s else None,
        })
    return result


# ─── SCORING V2 ──────────────────────────────────────────────────────────────

class CriterionSourceScoreIn(BaseModel):
    brand_id: int
    criterion_id: int
    source_id: Optional[int] = None
    tier: int
    judgment: str
    notes: Optional[str] = None


@app.post("/scoring/criterion-score")
def add_criterion_source_score(data: CriterionSourceScoreIn):
    if data.tier not in TIER_VALUES:
        raise HTTPException(status_code=400, detail="tier must be 1, 2 or 3")
    if data.judgment not in TIER_VALUES[1]:
        raise HTTPException(status_code=400, detail=f"judgment must be one of {list(TIER_VALUES[1].keys())}")

    value = TIER_VALUES[data.tier][data.judgment]
    label_en = SCORE_LABELS[data.judgment]["en"]
    label_it = SCORE_LABELS[data.judgment]["it"]

    try:
        supabase.table("criterion_source_scores").upsert({
            "brand_id": data.brand_id,
            "criterion_id": data.criterion_id,
            "source_id": data.source_id,
            "tier": data.tier,
            "value": value,
            "label_en": label_en,
            "label_it": label_it,
            "notes": data.notes,
            "status": "published",
            "updated_at": "now()",
        }, on_conflict="brand_id,criterion_id,source_id").execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = compute_brand_score_v2(data.brand_id)
    return {"ok": True, "value": value, **result}


@app.delete("/scoring/criterion-score/{brand_id}/{criterion_id}/{source_id}")
def delete_criterion_source_score(brand_id: int, criterion_id: int, source_id: int):
    """
    Rimuove una valutazione fonte/criterio e ricalcola il punteggio del brand.
    """
    try:
        supabase.table("criterion_source_scores") \
            .delete() \
            .eq("brand_id", brand_id) \
            .eq("criterion_id", criterion_id) \
            .eq("source_id", source_id) \
            .execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = compute_brand_score_v2(brand_id)
    return {"ok": True, **result}


@app.get("/scoring/criterion-scores/{brand_id}")
def get_criterion_scores(brand_id: int):
    css_res = supabase.table("criterion_source_scores") \
        .select("*, scoring_criteria(code, label_en, label_it, category_key), sources(url, title, publisher)") \
        .eq("brand_id", brand_id) \
        .eq("status", "published") \
        .execute()
    rows = css_res.data or []

    by_criterion = {}
    for r in rows:
        cid = r["criterion_id"]
        if cid not in by_criterion:
            by_criterion[cid] = {"criterion": r.get("scoring_criteria"), "sources": []}
        by_criterion[cid]["sources"].append({
            "source_id": r.get("source_id"),
            "source": r.get("sources"),
            "tier": r["tier"],
            "value": r["value"],
            "label_en": r["label_en"],
            "label_it": r["label_it"],
        })

    result = []
    for cid, data in by_criterion.items():
        css_rows = [{"tier": s["tier"], "value": s["value"], "status": "published"}
                    for s in data["sources"]]
        computed = compute_criterion_score(css_rows)
        result.append({
            "criterion_id": cid,
            "criterion": data["criterion"],
            "computed_score": computed["score"],
            "criteria_met": computed["criteria_met"],
            "tier_used": computed["tier_used"],
            "sources": data["sources"],
        })

    brand_res = supabase.table("brands").select("total_score_v2, criteria_published") \
        .eq("id", brand_id).single().execute()
    brand = brand_res.data or {}

    return {
        "brand_id": brand_id,
        "total_score_v2": brand.get("total_score_v2"),
        "criteria_published": brand.get("criteria_published", 0),
        "criteria": result,
    }


@app.post("/scoring/recalculate/{brand_id}")
def recalculate_brand_score(brand_id: int):
    result = compute_brand_score_v2(brand_id)
    return {"ok": True, "brand_id": brand_id, **result}


@app.post("/scoring/recalculate-all")
def recalculate_all_scores():
    brands_res = supabase.table("brands").select("id").execute()
    brands = brands_res.data or []
    results = []
    for b in brands:
        try:
            r = compute_brand_score_v2(b["id"])
            results.append({"brand_id": b["id"], **r})
        except Exception as e:
            results.append({"brand_id": b["id"], "error": str(e)})
    return {"ok": True, "processed": len(results), "results": results}


@app.get("/scoring/verdict")
def get_score_verdict(score: float, lang: str = "en"):
    return get_verdict(score, lang)


# ─── CONTRIBUTION ENDPOINTS ───────────────────────────────────────────────────

class BrandProposalIn(BaseModel):
    name: str
    sector_key: Optional[str] = None
    website: Optional[str] = None
    reason: Optional[str] = None
    submitter: Optional[str] = None

class SourceProposalIn(BaseModel):
    brand_id: int
    category_key: str
    url: str
    title: Optional[str] = None
    publisher: Optional[str] = None
    summary: Optional[str] = None
    submitter: Optional[str] = None

class ErrorReportIn(BaseModel):
    brand_id: int
    category_key: Optional[str] = None
    description: str
    source_url: Optional[str] = None
    submitter: Optional[str] = None


async def notify_contribution(type: str, data: dict):
    resend_key = os.getenv("RESEND_KEY")
    notify_email = os.getenv("NOTIFY_EMAIL")
    if not resend_key or not notify_email:
        return
    icons = {"brand": "🏷️", "source": "🔗", "error": "🚨"}
    titles = {"brand": "New brand proposal", "source": "New source proposal", "error": "New error report"}
    icon = icons.get(type, "📬")
    title = titles.get(type, "New contribution")
    rows = ""
    for key, val in data.items():
        if val:
            rows += f"<tr><td style='padding:6px 10px;color:#666;font-size:12px;white-space:nowrap'>{key}</td><td style='padding:6px 10px;font-size:12px'>{val}</td></tr>"
    html = f"""<div style="font-family:sans-serif;max-width:560px;margin:0 auto;color:#1a1a2e">
  <div style="background:#0f1a14;padding:18px 24px;border-radius:12px 12px 0 0;border-bottom:2px solid #63CAB7">
    <h2 style="color:#63CAB7;margin:0;font-size:16px;font-weight:600">{icon} EthicPrint — {title}</h2>
    <p style="color:rgba(255,255,255,0.4);margin:4px 0 0;font-size:12px">{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')} UTC</p>
  </div>
  <div style="background:#fff;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 12px 12px;padding:20px">
    <table style="width:100%;border-collapse:collapse;background:#f9f9f9;border-radius:8px;overflow:hidden">{rows}</table>
    <div style="margin-top:20px;text-align:center">
      <a href="https://ethicprint.org/admin.html" style="display:inline-block;background:#0f1a14;color:#63CAB7;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;border:1px solid #63CAB7">
        Review in admin →
      </a>
    </div>
  </div>
</div>"""
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient() as c:
            await c.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                json={"from": "EthicPrint <checker@ethicprint.org>", "to": [notify_email],
                      "subject": f"EthicPrint: {title}", "html": html},
                timeout=10,
            )
    except Exception as e:
        print(f"notify_contribution failed: {e}")


@app.post("/contribute/brand")
async def propose_brand(data: BrandProposalIn, background_tasks: BackgroundTasks):
    if not data.name or len(data.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Brand name too short")
    try:
        res = supabase.table("brand_proposals").insert({
            "name": data.name.strip(), "sector_key": data.sector_key,
            "website": data.website, "reason": data.reason,
            "submitter": data.submitter, "status": "pending",
        }).execute()
        new_id = res.data[0]["id"] if res.data else None
        background_tasks.add_task(notify_contribution, "brand", {
            "Brand": data.name.strip(), "Sector": data.sector_key or "—",
            "Website": data.website or "—", "Reason": data.reason or "—",
            "Submitted by": data.submitter or "anonymous",
        })
        return {"ok": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contribute/source")
async def propose_source_public(data: SourceProposalIn, background_tasks: BackgroundTasks):
    if not data.url or not data.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")
    brand_res = supabase.table("brands").select("id, name").eq("id", data.brand_id).limit(1).execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand_name = brand_res.data[0].get("name", str(data.brand_id))
    existing = supabase.table("sources").select("id").eq("url", data.url).execute()
    existing_prop = supabase.table("source_proposals").select("id").eq("url", data.url).execute()
    if existing.data or existing_prop.data:
        raise HTTPException(status_code=409, detail="Source already exists or proposed")
    try:
        res = supabase.table("source_proposals").insert({
            "brand_id": data.brand_id, "category_key": data.category_key,
            "url": data.url, "title": data.title,
            "publisher": data.publisher or "", "summary": data.summary or "",
            "status": "pending", "job_type": "new",
        }).execute()
        new_id = res.data[0]["id"] if res.data else None
        background_tasks.add_task(notify_contribution, "source", {
            "Brand": brand_name, "Category": data.category_key or "—",
            "URL": data.url, "Title": data.title or "—",
            "Publisher": data.publisher or "—", "Submitted by": data.submitter or "anonymous",
        })
        return {"ok": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contribute/error")
async def report_error(data: ErrorReportIn, background_tasks: BackgroundTasks):
    if not data.description or len(data.description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Description too short")
    brand_res = supabase.table("brands").select("id, name").eq("id", data.brand_id).limit(1).execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")
    brand_name = brand_res.data[0].get("name", str(data.brand_id))
    try:
        res = supabase.table("error_reports").insert({
            "brand_id": data.brand_id, "category_key": data.category_key,
            "description": data.description.strip(), "source_url": data.source_url,
            "submitter": data.submitter, "status": "pending",
        }).execute()
        new_id = res.data[0]["id"] if res.data else None
        background_tasks.add_task(notify_contribution, "error", {
            "Brand": brand_name, "Category": data.category_key or "—",
            "Description": data.description.strip(), "Source URL": data.source_url or "—",
            "Submitted by": data.submitter or "anonymous",
        })
        return {"ok": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contribute/brands-list")
def get_brands_for_contribute(lang: str = "en"):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    res = supabase.table("brands").select("id, name, logo, sectors(key, label, label_en)").order("name").execute()
    brands = res.data or []
    return [{"id": b["id"], "name": b["name"], "logo": b["logo"],
             "sector": (b.get("sectors") or {}).get("label_en" if lang == "en" else "label", "")}
            for b in brands]


@app.get("/contribute/pending")
def get_contributions_pending():
    brand_props = supabase.table("brand_proposals").select("*").eq("status", "pending") \
        .order("created_at", desc=True).execute().data or []
    error_reps = supabase.table("error_reports").select("*, brands(name, logo)").eq("status", "pending") \
        .order("created_at", desc=True).execute().data or []
    return {
        "brand_proposals": brand_props,
        "error_reports": error_reps,
        "counts": {"brand_proposals": len(brand_props), "error_reports": len(error_reps)}
    }


@app.post("/contribute/brand-proposal/{proposal_id}/resolve")
def resolve_brand_proposal(proposal_id: int, status: str = "approved"):
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")
    supabase.table("brand_proposals").update({"status": status}).eq("id", proposal_id).execute()
    return {"ok": True}


@app.post("/contribute/error-report/{report_id}/resolve")
def resolve_error_report(report_id: int, status: str = "resolved"):
    if status not in ("resolved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be resolved or rejected")
    supabase.table("error_reports").update({"status": status}).eq("id", report_id).execute()
    return {"ok": True}


# ─── REPLACEMENT SEARCH ───────────────────────────────────────────────────────

@app.post("/sources/{source_id}/find-replacement")
async def find_replacement(source_id: int):
    import httpx as _httpx
    source_res = supabase.table("sources").select("*, brands(name)").eq("id", source_id).single().execute()
    if not source_res.data:
        raise HTTPException(status_code=404, detail="Source not found")
    source = source_res.data
    brand_name = (source.get("brands") or {}).get("name", "")
    category_key = source.get("category_key", "")
    CAT_LABELS = {
        "armi": "arms weapons military contracts defense",
        "ambiente": "environment CO2 emissions climate sustainability",
        "diritti": "human rights labor rights workers conditions supply chain",
        "fisco": "tax avoidance tax haven fiscal transparency",
    }
    cat_desc = CAT_LABELS.get(category_key, category_key)
    year = __import__("datetime").datetime.now().year
    query = f"{brand_name} {cat_desc} {year-1}..{year}"
    brave_key = os.getenv("BRAVE_API_KEY")
    candidates = []
    if brave_key:
        try:
            async with _httpx.AsyncClient() as c:
                r = await c.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"Accept": "application/json", "X-Subscription-Token": brave_key},
                    params={"q": query, "count": 8, "search_lang": "en", "freshness": "py"},
                    timeout=10,
                )
                results = r.json().get("web", {}).get("results", [])
                candidates = [{"url": x.get("url"), "title": x.get("title"), "description": x.get("description", "")}
                               for x in results if x.get("url")]
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Brave search failed: {e}")
    if not candidates:
        return {"candidates": [], "query": query}
    existing_urls = {s["url"] for s in (supabase.table("sources").select("url").execute().data or [])}
    candidates = [c for c in candidates if c["url"] not in existing_urls]
    approved = []
    if ANTHROPIC_KEY:
        async with _httpx.AsyncClient() as c:
            for candidate in candidates[:6]:
                prompt = f"""You are evaluating a replacement source for EthicPrint.

Brand: {brand_name}
Category: {category_key} ({cat_desc})
Original broken source: {source.get('url', '')}

Candidate:
- URL: {candidate.get('url', '')}
- Title: {candidate.get('title', '')}
- Description: {candidate.get('description', '')}

Is this a relevant, credible replacement? Reply ONLY with JSON:
{{"relevant": true/false, "publisher": "name", "summary": "1 sentence", "tier": 1/2/3}}"""
                try:
                    r = await c.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=30,
                    )
                    text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
                    ev = __import__("json").loads(text)
                    if ev.get("relevant"):
                        approved.append({**candidate, "publisher": ev.get("publisher", ""),
                                         "summary": ev.get("summary", ""), "tier": ev.get("tier", 3)})
                    if len(approved) >= 3:
                        break
                except Exception:
                    continue
    return {"source_id": source_id, "brand_name": brand_name, "category_key": category_key,
            "query": query, "candidates": approved}


@app.post("/sources/{source_id}/propose-replacement")
def propose_replacement(source_id: int, data: dict):
    source_res = supabase.table("sources").select("brand_id, category_key").eq("id", source_id).single().execute()
    if not source_res.data:
        raise HTTPException(status_code=404, detail="Source not found")
    s = source_res.data
    try:
        res = supabase.table("source_proposals").insert({
            "brand_id": s["brand_id"], "category_key": s["category_key"],
            "url": data.get("url"), "title": data.get("title"),
            "publisher": data.get("publisher", ""), "summary": data.get("summary", ""),
            "status": "pending", "job_type": "replacement", "replaces_id": source_id,
        }).execute()
        return {"ok": True, "id": res.data[0]["id"] if res.data else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sources/{source_id}/mark-resolved")
def mark_source_resolved(source_id: int):
    supabase.table("sources").update({"broken": False, "content_missing": False}).eq("id", source_id).execute()
    return {"ok": True}
