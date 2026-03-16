from typing import Optional

from fastapi import APIRouter, Query, BackgroundTasks
from app.services.public_api import fetch_brands, fetch_brand_detail

router = APIRouter(tags=["brands"])


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
