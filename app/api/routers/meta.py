from fastapi import APIRouter
from app.services.meta import fetch_sectors

router = APIRouter(tags=["meta"])


@router.get("/sectors")
def get_sectors():
    return fetch_sectors()
