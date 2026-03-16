from typing import Optional

from fastapi import APIRouter, BackgroundTasks

from app.services.proposals import (
    fetch_source_proposals,
    revert_source_proposal_to_pending,
    approve_source_proposal,
)
from legacy_main import ApproveProposalBody, JUDGMENT_VALUES, JUDGMENT_LABELS_IT

router = APIRouter(tags=["proposals"])


@router.get("/source-proposals")
def get_source_proposals(status: str = "pending"):
    return fetch_source_proposals(status=status)


@router.patch("/source-proposals/{proposal_id}/revert")
def revert_proposal_to_pending(proposal_id: int):
    return revert_source_proposal_to_pending(proposal_id=proposal_id)


@router.post("/source-proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    background_tasks: BackgroundTasks,
    body: Optional[ApproveProposalBody] = None,
):
    return await approve_source_proposal(
        proposal_id=proposal_id,
        background_tasks=background_tasks,
        body=body,
        judgment_values=JUDGMENT_VALUES,
        judgment_labels_it=JUDGMENT_LABELS_IT,
    )
