from fastapi import APIRouter

from app.services.proposals import fetch_source_proposals

router = APIRouter(tags=["proposals"])


@router.get("/source-proposals")
def get_source_proposals(status: str = "pending"):
    return fetch_source_proposals(status=status)
