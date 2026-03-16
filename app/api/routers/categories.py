from fastapi import APIRouter
from app.services.public_api import fetch_categories

router = APIRouter(tags=["categories"])


@router.get("/categories")
def list_categories():
    return fetch_categories()
