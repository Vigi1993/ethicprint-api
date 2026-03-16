from fastapi import APIRouter
from app.services.meta import fetch_sectors, fetch_langs

router = APIRouter(tags=["meta"])


@router.get("/sectors")
def get_sectors():
    return fetch_sectors()


@router.get("/langs")
def get_langs():
    return fetch_langs()
