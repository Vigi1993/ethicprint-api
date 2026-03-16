from fastapi import APIRouter
from app.services.public_api import get_categories

router = APIRouter(tags=["categories"])


@router.get("/categories")
def list_categories():
    return get_categories()
