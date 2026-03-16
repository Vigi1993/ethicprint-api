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
