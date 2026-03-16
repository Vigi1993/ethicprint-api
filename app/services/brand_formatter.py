from app.services.scoring import weighted_confidence
from app.services.translations import apply_translation


def format_brand(brand: dict, sources: list = [], translation: dict = None, lang: str = "en") -> dict:
    if translation:
        brand = apply_translation(dict(brand), translation)

    sector = brand.get("sectors") or {}

    grouped_sources = {}
    for s in sources:
        key = s["category_key"]
        if key not in grouped_sources:
            grouped_sources[key] = []
        grouped_sources[key].append(
            {
                "url": s["url"],
                "title": s["title"],
                "publisher": s["publisher"],
                "published_at": s["published_at"],
                "tier": s.get("tier", 3),
            }
        )

    sector_label = (
        sector.get("label_en", "")
        if lang == "en" and sector.get("label_en")
        else sector.get("label", "")
    )

    confidence = weighted_confidence(sources)
    total_score_v2 = brand.get("total_score_v2")
    criteria_published = brand.get("criteria_published", 0) or 0

    cat_score_map = {
        "armi": brand.get("score_armi", 0) or 0,
        "ambiente": brand.get("score_ambiente", 0) or 0,
        "diritti": brand.get("score_diritti", 0) or 0,
        "fisco": brand.get("score_fisco", 0) or 0,
    }

    insufficient_data = total_score_v2 is None and criteria_published == 0

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
