from fastapi import APIRouter

from app.services.source_maintenance import (
    find_source_replacement,
    create_replacement_proposal,
    mark_source_resolved,
)

router = APIRouter(tags=["source-maintenance"])


@router.post("/sources/{source_id}/find-replacement")
async def find_replacement(source_id: int):
    return await find_source_replacement(source_id)


@router.post("/sources/{source_id}/propose-replacement")
def propose_replacement(source_id: int, data: dict):
    return create_replacement_proposal(source_id=source_id, data=data)


@router.post("/sources/{source_id}/mark-resolved")
def mark_resolved(source_id: int):
    return mark_source_resolved(source_id)
