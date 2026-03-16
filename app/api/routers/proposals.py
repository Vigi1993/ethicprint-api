from fastapi import APIRouter

from app.services.proposals import (
    fetch_source_proposals,
    revert_source_proposal_to_pending,
)

router = APIRouter(tags=["proposals"])


@router.get("/source-proposals")
def get_source_proposals(status: str = "pending"):
    return fetch_source_proposals(status=status)


@router.patch("/source-proposals/{proposal_id}/revert")
def revert_proposal_to_pending(proposal_id: int):
    return revert_source_proposal_to_pending(proposal_id=proposal_id)
