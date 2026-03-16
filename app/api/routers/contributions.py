from fastapi import APIRouter, BackgroundTasks

from app.services.contributions import (
    create_brand_proposal,
    create_source_proposal,
    create_error_report,
    fetch_brands_for_contribute,
    fetch_contributions_pending,
    resolve_brand_proposal,
    resolve_error_report,
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


@router.get("/contribute/brands-list")
def get_brands_for_contribute(lang: str = "en"):
    return fetch_brands_for_contribute(lang=lang)

@router.post("/contribute/brand-proposal/{proposal_id}/resolve")
def resolve_brand_proposal_endpoint(proposal_id: int, status: str = "approved"):
    return resolve_brand_proposal(proposal_id=proposal_id, status=status)


@router.get("/contribute/pending")
def get_contributions_pending():
    return fetch_contributions_pending()

@router.post("/contribute/error-report/{report_id}/resolve")
def resolve_error_report_endpoint(report_id: int, status: str = "resolved"):
    return resolve_error_report(report_id=report_id, status=status)
