from typing import Optional

from fastapi import APIRouter, Query

from app.services.scoring_read import (
    fetch_scoring_criteria,
    fetch_brand_scores,
    fetch_criterion_scores,
    fetch_score_verdict,
)
from app.services.scoring_write import create_criterion_source_score
from legacy_main import CriterionSourceScoreIn

router = APIRouter(tags=["scoring"])


@router.get("/scoring-criteria")
def get_scoring_criteria():
    return fetch_scoring_criteria()


@router.get("/brands/{brand_id}/scores")
def get_brand_scores(brand_id: int, lang: Optional[str] = Query("en")):
    return fetch_brand_scores(brand_id=brand_id, lang=lang)


@router.get("/scoring/criterion-scores/{brand_id}")
def get_criterion_scores(brand_id: int):
    return fetch_criterion_scores(brand_id)


@router.get("/scoring/verdict")
def get_score_verdict(score: float, lang: str = Query("en")):
    return fetch_score_verdict(score=score, lang=lang)


@router.post("/scoring/criterion-score")
def add_criterion_source_score(data: CriterionSourceScoreIn):
    return create_criterion_source_score(data)
