from fastapi import APIRouter

from app.services.scoring_read import fetch_scoring_criteria

router = APIRouter(tags=["scoring"])


@router.get("/scoring-criteria")
def get_scoring_criteria():
    return fetch_scoring_criteria()
