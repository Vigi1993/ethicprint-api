from typing import Optional

from fastapi import HTTPException, BackgroundTasks

from app.core.constants import SUPPORTED_LANGS, DEFAULT_LANG
from app.integrations.supabase_client import supabase
from app.services.scoring import (
    weighted_confidence,
    compute_criterion_score,
    source_confidence_v2,
)
from app.services.brand_formatter import format_brand
from app.services.translations import get_translation, generate_and_save_translation
from app.services.ai_tasks import generate_impact_summary
from app.services.alternatives import smart_alternatives
from app.core.config import settings


def fetch_brands(
    sector: Optional[str] = None,
    search: Optional[str] = None,
    lang: Optional[str] = "en",
):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    query = supabase.table("brands").select("*, sectors(key, label, label_en, icon)")

    if sector:
        sector_res = (
            supabase.table("sectors")
            .select("id")
            .eq("key", sector)
            .single()
            .execute()
        )
        if not sector_res.data:
            raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
        query = query.eq("sector_id", sector_res.data["id"])

    res = query.order("name").execute()
    brands = res.data or []

    if search:
        search_lower = search.lower()
        brands = [b for b in brands if search_lower in b["name"].lower()]

    if lang != DEFAULT_LANG:
        translations_res = (
            supabase.table("brand_translations")
            .select("*")
            .eq("lang", lang)
            .execute()
        )
        translations = {t["brand_id"]: t for t in (translations_res.data or [])}
        return [
            format_brand(b, translation=translations.get(b["id"]), lang=lang)
            for b in brands
        ]

    return [format_brand(b, lang=lang) for b in brands]


async def fetch_brand_detail(
    brand_id: int,
    lang: Optional[str] = "en",
    background_tasks: BackgroundTasks = None,
):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    brand_res = (
        supabase.table("brands")
        .select("*, sectors(key, label, label_en, icon)")
        .eq("id", brand_id)
        .single()
        .execute()
    )
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    # fonte di verità della BrandCard = solo score v2 pubblicati
    css_res = (
        supabase.table("criterion_source_scores")
        .select(
            "criterion_id, source_id, tier, value, status, scoring_criteria(category_key)"
        )
        .eq("brand_id", brand_id)
        .eq("status", "published")
        .execute()
    )
    css_rows = css_res.data or []

    source_ids = list(
        {
            row["source_id"]
            for row in css_rows
            if row.get("source_id") is not None
        }
    )

    published_sources = []
    if source_ids:
        sources_res = (
            supabase.table("sources")
            .select("id, url, title, publisher, published_at")
            .in_("id", source_ids)
            .neq("broken", True)
            .neq("content_missing", True)
            .execute()
        )
        source_map = {s["id"]: s for s in (sources_res.data or [])}

        for row in css_rows:
            src = source_map.get(row.get("source_id"))
            if not src:
                continue

            category_key = (row.get("scoring_criteria") or {}).get("category_key")
            published_sources.append(
                {
                    "id": src["id"],
                    "url": src.get("url"),
                    "title": src.get("title"),
                    "publisher": src.get("publisher"),
                    "published_at": src.get("published_at"),
                    "category_key": category_key,
                    "tier": row.get("tier", 3),
                }
            )

    translation = None
    if lang != DEFAULT_LANG:
        translation = get_translation(brand_id, lang)
        if not translation and background_tasks and settings.ANTHROPIC_API_KEY:
            background_tasks.add_task(
                generate_and_save_translation,
                brand_id,
                brand_res.data,
                lang,
            )

    formatted = format_brand(
        brand_res.data,
        published_sources,
        translation,
        lang=lang,
    )

    formatted["confidence"] = source_confidence_v2(css_rows)

    if not brand_res.data.get("impact_summary_en") and background_tasks and settings.ANTHROPIC_API_KEY:
        try:
            by_crit = {}
            for r in css_rows:
                cid = r["criterion_id"]
                if cid not in by_crit:
                    by_crit[cid] = {
                        "criterion": r.get("scoring_criteria"),
                        "rows": [],
                    }
                by_crit[cid]["rows"].append(r)

            criterion_scores = []
            for cid, d in by_crit.items():
                comp = compute_criterion_score(d["rows"])
                criterion_scores.append(
                    {
                        "criterion_id": cid,
                        "criterion": d["criterion"],
                        "computed_score": comp["score"],
                        "criteria_met": comp["criteria_met"],
                    }
                )
        except Exception:
            criterion_scores = []

        background_tasks.add_task(
            generate_impact_summary,
            brand_id,
            brand_res.data,
            criterion_scores,
        )

    sector_id = brand_res.data.get("sector_id")
    if sector_id:
        formatted["alternatives"] = smart_alternatives(brand_id, sector_id, lang)

    return formatted

def fetch_categories():
    res = (
        supabase.table("categories")
        .select("*")
        .eq("active", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []


from app.services.scoring import detect_tier


def fetch_public_sources():
    res = (
        supabase.table("sources")
        .select("id, url, title, publisher, published_at, category_key, tier, brand_id, brands(name)")
        .neq("broken", True)
        .neq("content_missing", True)
        .order("tier")
        .execute()
    )

    sources = res.data or []

    for s in sources:
        if not s.get("tier"):
            s["tier"] = detect_tier(s.get("publisher", ""))

    total = len(sources)

    by_tier = {1: [], 2: [], 3: []}

    for s in sources:
        t = s.get("tier", 3)
        by_tier[t if t in [1, 2, 3] else 3].append(s)

    return {
        "total": total,
        "tier1": by_tier[1],
        "tier2": by_tier[2],
        "tier3": by_tier[3],
    }
