from fastapi import APIRouter, BackgroundTasks

from app.services.contributions import create_brand_proposal
from legacy_main import BrandProposalIn

router = APIRouter(tags=["contributions"])


@router.post("/contribute/brand")
async def propose_brand(data: BrandProposalIn, background_tasks: BackgroundTasks):
    return await create_brand_proposal(data=data, background_tasks=background_tasks)
