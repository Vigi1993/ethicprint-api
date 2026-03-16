from fastapi import APIRouter

from app.services.brand_sources import fetch_brand_sources

router = APIRouter(tags=["brand-sources"])


@router.get("/brands/{brand_id}/sources")
def get_brand_sources(brand_id: int):
    return fetch_brand_sources(brand_id)
