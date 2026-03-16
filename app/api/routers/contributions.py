from fastapi import APIRouter, BackgroundTasks

from app.services.contributions import create_brand_proposal, create_source_proposal
from legacy_main import BrandProposalIn, SourceProposalIn

router = APIRouter(tags=["contributions"])


@router.post("/contribute/brand")
async def propose_brand(data: BrandProposalIn, background_tasks: BackgroundTasks):
    return await create_brand_proposal(data=data, background_tasks=background_tasks)


@router.post("/contribute/source")
async def propose_source_public(data: SourceProposalIn, background_tasks: BackgroundTasks):
    return await create_source_proposal(data=data, background_tasks=background_tasks)
