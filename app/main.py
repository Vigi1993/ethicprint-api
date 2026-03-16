from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routers.brands import router as brands_router
from app.api.routers.categories import router as categories_router
from app.api.routers.sources import router as sources_router
from app.api.routers.meta import router as meta_router
from app.api.routers.brand_sources import router as brand_sources_router
from app.api.routers.scoring import router as scoring_router

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

origins = ["*"] if settings.APP_CORS_ORIGINS == "*" else [
    origin.strip() for origin in settings.APP_CORS_ORIGINS.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brands_router)
app.include_router(categories_router)
app.include_router(sources_router)
app.include_router(meta_router)
app.include_router(brand_sources_router)
app.include_router(scoring_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
