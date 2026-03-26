from fastapi import APIRouter
from app.services.meta import fetch_sectors, fetch_langs, fetch_publishers

router = APIRouter(tags=["meta"])


@router.get("/sectors")
def get_sectors():
    return fetch_sectors()


@router.get("/langs")
def get_langs():
    return fetch_langs()


@router.get("/publishers")
def get_publishers():
    return fetch_publishers()

@router.get("/recent-source-updates")
def recent_source_updates(limit: int = 20):
    from app.services.meta import get_recent_source_updates
    return get_recent_source_updates(limit=min(limit, 50))
