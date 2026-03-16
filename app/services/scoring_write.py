from fastapi import HTTPException

from app.core.constants import TIER_VALUES, SCORE_LABELS
from app.integrations.supabase_client import supabase
from app.services.scoring import compute_brand_score_v2


def create_criterion_source_score(data):
    if data.tier not in TIER_VALUES:
        raise HTTPException(status_code=400, detail="tier must be 1, 2 or 3")

    if data.judgment not in TIER_VALUES[1]:
        raise HTTPException(
            status_code=400,
            detail=f"judgment must be one of {list(TIER_VALUES[1].keys())}",
        )

    value = TIER_VALUES[data.tier][data.judgment]
    label_en = SCORE_LABELS[data.judgment]["en"]
    label_it = SCORE_LABELS[data.judgment]["it"]

    try:
        supabase.table("criterion_source_scores").upsert(
            {
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
            },
            on_conflict="brand_id,criterion_id,source_id",
        ).execute()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = compute_brand_score_v2(data.brand_id)
    return {"ok": True, "value": value, **result}

def delete_criterion_source_score(brand_id: int, criterion_id: int, source_id: int):
    """
    Rimuove una valutazione fonte/criterio e ricalcola il punteggio del brand.
    """
    try:
        (
            supabase.table("criterion_source_scores")
            .delete()
            .eq("brand_id", brand_id)
            .eq("criterion_id", criterion_id)
            .eq("source_id", source_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = compute_brand_score_v2(brand_id)
    return {"ok": True, **result}
