from app.services.scoring import weighted_confidence
from app.services.translations import apply_translation
from app.core.judgments import raw_score_to_public_score, public_score_label

V2_CATEGORY_KEYS = ["armi", "ambiente", "diritti", "fisco"]

def _group_sources_by_category(sources: list) -> dict:
    grouped_sources = {}
    for s in sources:
        key = s["category_key"]
        grouped_sources.setdefault(key, []).append(
            {
                "url": s.get("url"),
                "title": s.get("title"),
                "publisher": s.get("publisher"),
                "published_at": s.get("published_at"),
                "tier": s.get("tier", 3),
            }
        )
    return grouped_sources

def _build_v2_category_scores(brand: dict) -> dict:
    # Se in futuro salvi category scores v2 già sul brand, leggili qui.
    # Per ora fallback safe: se non esistono, torna None per evitare falsi 0.
    raw = brand.get("category_scores_v2")
    if isinstance(raw, dict):
        return {k: raw.get(k) for k in V2_CATEGORY_KEYS}

    return {k: None for k in V2_CATEGORY_KEYS}

def _build_notes(brand: dict) -> dict:
    return {
        "armi": brand.get("note_armi"),
        "ambiente": brand.get("note_ambiente"),
        "diritti": brand.get("note_diritti"),
        "fisco": brand.get("note_fisco"),
    }

def format_brand(
    brand: dict,
    sources: list = [],
    translation: dict = None,
    lang: str = "en",
) -> dict:
    if translation:
        brand = apply_translation(dict(brand), translation)

    sector = brand.get("sectors") or {}
    grouped_sources = _group_sources_by_category(sources)

    sector_label = (
        sector.get("label_en", "")
        if lang == "en" and sector.get("label_en")
        else sector.get("label", "")
    )

    confidence = weighted_confidence(sources)
    total_score_v2 = brand.get("total_score_v2")
    criteria_published = brand.get("criteria_published", 0) or 0
    public_score = (
    raw_score_to_public_score(total_score_v2)
    if criteria_published > 0
    else None
    )
    public_label = public_score_label(public_score, lang)
    insufficient_data = total_score_v2 is None and criteria_published == 0

    return {
        "id": brand["id"],
        "name": brand["name"],
        "sector": sector_label,
        "sector_key": sector.get("key", ""),
        "sector_icon": sector.get("icon", ""),
        "logo": brand.get("logo"),
        "parent": brand.get("parent"),
        "scores": _build_v2_category_scores(brand),
        "total_score": total_score_v2,
        "criteria_published": criteria_published,
        "insufficient_data": insufficient_data,
        "notes": _build_notes(brand),
        "sources": grouped_sources,
        "confidence": confidence,
        "impact_summary": (
            brand.get(f"impact_summary_{lang}")
            or brand.get("impact_summary_en")
            or ""
        ),
        "alternatives": [],
        "last_updated": brand.get("last_updated"),
        "public_score": public_score,
        "public_label": public_label,
    }
