from fastapi import APIRouter, Query

from app.services.source_maintenance import (
    find_source_replacement,
    create_replacement_proposal,
    mark_source_resolved,
    exclude_source_from_criterion,
    remove_source_exclusion,
)
from legacy_main import ExclusionIn

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


@router.post("/sources/{source_id}/exclude-criterion")
def exclude_criterion(source_id: int, data: ExclusionIn):
    return exclude_source_from_criterion(source_id=source_id, data=data)


@router.delete("/sources/{source_id}/exclude-criterion/{criterion_id}")
def remove_exclusion(source_id: int, criterion_id: int, brand_id: int = Query(...)):
    return remove_source_exclusion(
        source_id=source_id,
        criterion_id=criterion_id,
        brand_id=brand_id,
    )
