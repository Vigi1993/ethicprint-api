from typing import Optional

from app.core.constants import SUPPORTED_LANGS, DEFAULT_LANG, SCORE_LABELS
from app.integrations.supabase_client import supabase
from app.services.scoring import compute_criterion_score


def fetch_scoring_criteria():
    res = (
        supabase.table("scoring_criteria")
        .select("*")
        .eq("active", True)
        .order("category_key")
        .order("sort_order")
        .execute()
    )

    data = res.data or []

    grouped = {}
    for c in data:
        key = c["category_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)

    return {"criteria": data, "grouped": grouped}


def fetch_brand_scores(brand_id: int, lang: Optional[str] = "en"):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    criteria_res = (
        supabase.table("scoring_criteria")
        .select("*")
        .eq("active", True)
        .order("category_key")
        .order("sort_order")
        .execute()
    )
    all_criteria = criteria_res.data or []

    scores_res = (
        supabase.table("brand_scores")
        .select("*")
        .eq("brand_id", brand_id)
        .eq("status", "published")
        .execute()
    )
    scores_by_criterion = {row["criterion_id"]: row for row in (scores_res.data or [])}

    result = {}
    for c in all_criteria:
        key = c["category_key"]
        if key not in result:
            result[key] = []

        s = scores_by_criterion.get(c["id"])
        label_key = f"label_{lang}" if lang != "en" else "label_en"

        result[key].append(
            {
                "criterion_id": c["id"],
                "code": c["code"],
                "label": c[label_key] if label_key in c else c["label_en"],
                "score": s["score"] if s else 3,
                "label_score": (
                    s[f"label_{lang}"]
                    if s and lang != "en" and s.get(f"label_{lang}")
                    else s["label_en"] if s else ""
                ),
                "notes": s["notes"] if s else None,
                "last_updated": s["last_updated"] if s else None,
            }
        )

    return result


def fetch_criterion_scores(brand_id: int):
    css_res = (
        supabase.table("criterion_source_scores")
        .select("*, scoring_criteria(code, label_en, label_it, category_key), sources(url, title, publisher)")
        .eq("brand_id", brand_id)
        .eq("status", "published")
        .execute()
    )
    rows = css_res.data or []

    by_criterion = {}
    for r in rows:
        cid = r["criterion_id"]
        if cid not in by_criterion:
            by_criterion[cid] = {"criterion": r.get("scoring_criteria"), "sources": []}
        by_criterion[cid]["sources"].append(
            {
                "source_id": r.get("source_id"),
                "source": r.get("sources"),
                "tier": r["tier"],
                "value": r["value"],
                "label_en": r["label_en"],
                "label_it": r["label_it"],
            }
        )

    result = []
    for cid, data in by_criterion.items():
        css_rows = [
            {"tier": s["tier"], "value": s["value"], "status": "published"}
            for s in data["sources"]
        ]
        computed = compute_criterion_score(css_rows)
        result.append(
            {
                "criterion_id": cid,
                "criterion": data["criterion"],
                "computed_score": computed["score"],
                "criteria_met": computed["criteria_met"],
                "tier_used": computed["tier_used"],
                "sources": data["sources"],
            }
        )

    brand_res = (
        supabase.table("brands")
        .select("total_score_v2, criteria_published")
        .eq("id", brand_id)
        .single()
        .execute()
    )
    brand = brand_res.data or {}

    return {
        "brand_id": brand_id,
        "total_score_v2": brand.get("total_score_v2"),
        "criteria_published": brand.get("criteria_published", 0),
        "criteria": result,
    }
