from typing import Optional

from fastapi import APIRouter, Query

from app.services.scoring_read import fetch_scoring_criteria, fetch_brand_scores

router = APIRouter(tags=["scoring"])


@router.get("/scoring-criteria")
def get_scoring_criteria():
    return fetch_scoring_criteria()


@router.get("/brands/{brand_id}/scores")
def get_brand_scores(brand_id: int, lang: Optional[str] = Query("en")):
    return fetch_brand_scores(brand_id=brand_id, lang=lang)
