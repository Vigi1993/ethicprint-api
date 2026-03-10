from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="EthicPrint API",
    description="API per il punteggio etico dei brand",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ethicprint.org", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── UTILS ────────────────────────────────────────────────────────────────────

def format_brand(brand: dict, sources: list = []) -> dict:
    """Trasforma una riga del DB nel formato usato dal frontend."""
    sector = brand.get("sectors") or {}
    grouped_sources = {}
    for s in sources:
        key = s["category_key"]
        if key not in grouped_sources:
            grouped_sources[key] = []
        grouped_sources[key].append({
            "url": s["url"],
            "title": s["title"],
            "publisher": s["publisher"],
            "published_at": s["published_at"],
        })

    return {
        "id": brand["id"],
        "name": brand["name"],
        "sector": sector.get("label", ""),
        "sector_key": sector.get("key", ""),
        "sector_icon": sector.get("icon", ""),
        "logo": brand["logo"],
        "parent": brand["parent"],
        "scores": {
            "armi": brand["score_armi"],
            "ambiente": brand["score_ambiente"],
            "diritti": brand["score_diritti"],
            "fisco": brand["score_fisco"],
        },
        "notes": {
            "armi": brand["note_armi"],
            "ambiente": brand["note_ambiente"],
            "diritti": brand["note_diritti"],
            "fisco": brand["note_fisco"],
        },
        "sources": grouped_sources,
        "alternatives": brand["alternatives"] or [],
        "last_updated": brand["last_updated"],
    }


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "EthicPrint API v1.0.0 — ethicprint.org"}


@app.get("/brands")
def get_brands(
    sector: Optional[str] = Query(None, description="Filtra per sector key"),
    search: Optional[str] = Query(None, description="Cerca per nome brand"),
):
    """Ritorna tutti i brand con settore e punteggi. Supporta filtro per settore e ricerca per nome."""
    query = supabase.table("brands").select("*, sectors(key, label, icon)")

    if sector:
        # join su sectors per filtrare per key
        sector_res = supabase.table("sectors").select("id").eq("key", sector).single().execute()
        if not sector_res.data:
            raise HTTPException(status_code=404, detail=f"Settore '{sector}' non trovato")
        query = query.eq("sector_id", sector_res.data["id"])

    res = query.order("name").execute()
    brands = res.data or []

    if search:
        search_lower = search.lower()
        brands = [b for b in brands if search_lower in b["name"].lower()]

    return [format_brand(b) for b in brands]


@app.get("/brands/{brand_id}")
def get_brand(brand_id: int):
    """Ritorna un singolo brand con punteggi, note, fonti e alternative."""
    brand_res = supabase.table("brands")\
        .select("*, sectors(key, label, icon)")\
        .eq("id", brand_id)\
        .single()\
        .execute()

    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand non trovato")

    sources_res = supabase.table("sources")\
        .select("*")\
        .eq("brand_id", brand_id)\
        .order("category_key")\
        .execute()

    return format_brand(brand_res.data, sources_res.data or [])


@app.get("/sectors")
def get_sectors():
    """Ritorna tutti i settori attivi con conteggio brand."""
    res = supabase.table("sectors")\
        .select("*")\
        .eq("active", True)\
        .order("sort_order")\
        .execute()
    return res.data or []


@app.get("/categories")
def get_categories():
    """Ritorna tutte le categorie etiche attive."""
    res = supabase.table("categories")\
        .select("*")\
        .eq("active", True)\
        .order("sort_order")\
        .execute()
    return res.data or []


@app.get("/brands/{brand_id}/sources")
def get_brand_sources(brand_id: int):
    """Ritorna tutte le fonti di un brand, raggruppate per categoria."""
    brand_res = supabase.table("brands").select("id").eq("id", brand_id).single().execute()
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand non trovato")

    res = supabase.table("sources")\
        .select("*")\
        .eq("brand_id", brand_id)\
        .order("category_key")\
        .execute()

    grouped = {}
    for s in (res.data or []):
        key = s["category_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append({
            "id": s["id"],
            "url": s["url"],
            "title": s["title"],
            "publisher": s["publisher"],
            "published_at": s["published_at"],
        })

    return grouped


@app.post("/suggest")
def suggest_brand(payload: dict):
    """Endpoint per suggerire un nuovo brand da aggiungere (va in revisione)."""
    required = ["name", "sector", "reason"]
    for field in required:
        if field not in payload or not payload[field]:
            raise HTTPException(status_code=422, detail=f"Campo '{field}' obbligatorio")

    # Per ora salviamo in una tabella suggestions (da creare) o logghiamo
    # TODO: quando aggiungi tabella suggestions, inserire qui
    return {
        "message": "Grazie per il suggerimento! Sarà revisionato da Marco.",
        "brand": payload.get("name")
    }
