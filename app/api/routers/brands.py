from fastapi import APIRouter, Query
from app.services.public_api import get_brands, get_brand_detail

router = APIRouter(tags=["brands"])


@router.get("/brands")
def list_brands(lang: str = Query("en")):
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    lang: Optional[str] = Query("en"),
):
    return fetch_brands(sector=sector, search=search, lang=lang)


@router.get("/brands/{brand_id}")
def brand_detail(brand_id: int, lang: str = Query("en")):
    return fetch_brand_detail(brand_id=brand_id, lang=lang)
