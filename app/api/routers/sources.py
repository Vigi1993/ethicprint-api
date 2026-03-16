from fastapi import APIRouter
from app.services.public_api import get_public_sources_summary

router = APIRouter(tags=["sources"])


@router.get("/sources/public")
def public_sources():
    return get_public_sources_summary()
