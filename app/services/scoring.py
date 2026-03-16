from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.constants import (
    CATS,
    FRESHNESS_MONTHS,
    TIER_WEIGHTS,
    VERDICTS,
)
from app.integrations.supabase_client import supabase


_publishers_cache: dict[str, int] = {}
_publishers_cache_time: float = 0.0


def _load_publishers() -> dict[str, int]:
    import time

    global _publishers_cache, _publishers_cache_time

    now = time.time()
    if _publishers_cache and (now - _publishers_cache_time) < 3600:
        return _publishers_cache

    try:
        res = (
            supabase.table("publishers")
            .select("name, tier")
            .eq("active", True)
            .execute()
        )
        cache: dict[str, int] = {}
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


def compute_criterion_score(css_rows: list[dict[str, Any]]) -> dict[str, Any]:
    published = [r for r in css_rows if r.get("status") == "published"]
    t1 = [r for r in published if r.get("tier") == 1]
    t2 = [r for r in published if r.get("tier") == 2]
    t3 = [r for r in published if r.get("tier", 3) == 3]

    def avg(rows: list[dict[str, Any]]) -> float:
        return sum(r["value"] for r in rows) / len(rows)

    if t1:
        score = avg(t1)
        tier_used = 1
        criteria_met = True
    elif len(t2) >= 2:
        score = avg(t2)
        tier_used = 2
        criteria_met = True
    elif len(t2) == 1 and len(t3) >= 3:
        score = t2[0]["value"] + avg(t3)
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
        "t1": len(t1),
        "t2": len(t2),
        "t3": len(t3),
    }


def compute_brand_score_v2(brand_id: int) -> dict[str, Any]:
    css_res = (
        supabase.table("criterion_source_scores")
        .select("criterion_id, tier, value, status, scoring_criteria(category_key)")
        .eq("brand_id", brand_id)
        .execute()
    )

    all_css = css_res.data or []
    by_criterion: dict[int, list[dict[str, Any]]] = {}

    for row in all_css:
        cid = row["criterion_id"]
        by_criterion.setdefault(cid, []).append(row)

    total = 0.0
    criteria_published = 0
    criterion_results: dict[int, dict[str, Any]] = {}

    for cid, rows in by_criterion.items():
        result = compute_criterion_score(rows)
        criterion_results[cid] = result

        if result["criteria_met"] and result["score"] is not None:
            total += result["score"]
            criteria_published += 1

        (
            supabase.table("brand_scores")
            .upsert(
                {
                    "brand_id": brand_id,
                    "criterion_id": cid,
                    "computed_score": result["score"],
                    "criteria_met": True,
                    "status": "published",
                    "last_updated": "now()",
                },
                on_conflict="brand_id,criterion_id",
            )
            .execute()
        )

    total_rounded = round(total, 1)

    (
        supabase.table("brands")
        .update(
            {
                "total_score_v2": total_rounded,
                "criteria_published": criteria_published,
                "last_updated": "now()",
            }
        )
        .eq("id", brand_id)
        .execute()
    )

    return {
        "total_score_v2": total_rounded,
        "criteria_published": criteria_published,
        "criterion_results": criterion_results,
    }


def get_verdict(score: float, lang: str = "en") -> dict[str, str]:
    for low, high, label_en, label_it, emoji in VERDICTS:
        if low <= score <= high:
            return {
                "label": label_en if lang == "en" else label_it,
                "emoji": emoji,
                "band": label_en,
            }
    return {"label": "Unknown", "emoji": "❓", "band": "Unknown"}


def source_confidence_v2(css_rows: list[dict[str, Any]]) -> dict[str, Any]:
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_MONTHS * 30)

    result: dict[str, Any] = {}
    for cat in CATS:
        cat_rows = [
            r for r in css_rows
            if (r.get("scoring_criteria") or {}).get("category_key") == cat
            and r.get("status") == "published"
        ]

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
            "level": level,
            "criteria_met": met,
            "label_en": {
                "high": "High confidence",
                "medium": "Medium confidence",
                "low": "Low confidence",
                "none": "No sources yet",
            }[level],
            "label_it": {
                "high": "Alta affidabilità",
                "medium": "Attendibilità media",
                "low": "Bassa affidabilità",
                "none": "Nessuna fonte",
            }[level],
            "count": total,
            "t1": t1,
            "t2": t2,
            "t3": t3,
        }

    return result


def weighted_confidence(sources: list[dict[str, Any]]) -> dict[str, Any]:
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_MONTHS * 30)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for s in sources:
        key = s.get("category_key")
        grouped.setdefault(key, []).append(s)

    result: dict[str, Any] = {}
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
            "criteria_met": met,
            "data_status": "ok" if met else ("insufficient" if count == 1 else "none"),
            "fresh_count": fresh_count,
            "label_en": {
                "high": "High confidence",
                "medium": "Medium confidence",
                "low": "Low confidence",
                "none": "No sources yet",
            }[level],
            "label_it": {
                "high": "Alta affidabilità",
                "medium": "Attendibilità media",
                "low": "Bassa affidabilità",
                "none": "Nessuna fonte",
            }[level],
            "count": count,
            "weighted_score": weighted,
            "tier1": t1,
            "tier2": t2,
            "tier3": t3,
        }

    return result
