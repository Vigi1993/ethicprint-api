from fastapi import APIRouter
from app.services.public_api import fetch_public_sources

router = APIRouter(tags=["sources"])


@router.get("/sources/public")
def public_sources():
    return fetch_public_sources()
