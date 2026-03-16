from fastapi import APIRouter, BackgroundTasks

from app.services.contributions import (
    create_brand_proposal,
    create_source_proposal,
    create_error_report,
)
from legacy_main import BrandProposalIn, SourceProposalIn, ErrorReportIn

router = APIRouter(tags=["contributions"])


@router.post("/contribute/brand")
async def propose_brand(data: BrandProposalIn, background_tasks: BackgroundTasks):
    return await create_brand_proposal(data=data, background_tasks=background_tasks)


@router.post("/contribute/source")
async def propose_source_public(data: SourceProposalIn, background_tasks: BackgroundTasks):
    return await create_source_proposal(data=data, background_tasks=background_tasks)


@router.post("/contribute/error")
async def report_error(data: ErrorReportIn, background_tasks: BackgroundTasks):
    return await create_error_report(data=data, background_tasks=background_tasks)
