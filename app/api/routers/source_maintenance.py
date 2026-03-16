from fastapi import APIRouter

from app.services.source_maintenance import find_source_replacement

router = APIRouter(tags=["source-maintenance"])


@router.post("/sources/{source_id}/find-replacement")
async def find_replacement(source_id: int):
    return await find_source_replacement(source_id)
