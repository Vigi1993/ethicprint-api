from typing import Optional

from fastapi import APIRouter, Query, BackgroundTasks
from app.services.public_api import fetch_brands, fetch_brand_detail
from datetime import datetime, timezone

router = APIRouter(tags=["brands"])


@router.post("/{brand_id}/abandon")
def abandon_brand(brand_id: int):
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    try:
        # Upsert — se esiste incrementa, altrimenti crea
        supabase.rpc("increment_abandonment", {
            "p_brand_id": brand_id,
            "p_year": year,
            "p_month": month,
        }).execute()

        res = (
            supabase.table("brand_abandonments")
            .select("count")
            .eq("brand_id", brand_id)
            .eq("year", year)
            .eq("month", month)
            .single()
            .execute()
        )
        return {"ok": True, "count": res.data["count"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{brand_id}/abandon-count")
def get_abandon_count(brand_id: int):
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    try:
        res = (
            supabase.table("brand_abandonments")
            .select("count")
            .eq("brand_id", brand_id)
            .eq("year", year)
            .eq("month", month)
            .maybeSingle()
            .execute()
        )
        count = res.data["count"] if res.data else 0
        return {"count": count}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/brands")
def list_brands(
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    lang: Optional[str] = Query("en"),
):
    return fetch_brands(sector=sector, search=search, lang=lang)


@router.get("/brands/{brand_id}")
async def brand_detail(
    brand_id: int,
    lang: Optional[str] = Query("en"),
    background_tasks: BackgroundTasks = None,
):
    return await fetch_brand_detail(
        brand_id=brand_id,
        lang=lang,
        background_tasks=background_tasks,
    )
