from app.integrations.supabase_client import supabase


def fetch_brands(
    sector: Optional[str] = None,
    search: Optional[str] = None,
    lang: Optional[str] = "en",
):
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

    query = supabase.table("brands").select("*, sectors(key, label, label_en, icon)")

    if sector:
        sector_res = (
            supabase.table("sectors")
            .select("id")
            .eq("key", sector)
            .single()
            .execute()
        )
        if not sector_res.data:
            raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")
        query = query.eq("sector_id", sector_res.data["id"])

    res = query.order("name").execute()
    brands = res.data or []

    if search:
        search_lower = search.lower()
        brands = [b for b in brands if search_lower in b["name"].lower()]

    if lang != DEFAULT_LANG:
        translations_res = (
            supabase.table("brand_translations")
            .select("*")
            .eq("lang", lang)
            .execute()
        )
        translations = {t["brand_id"]: t for t in (translations_res.data or [])}
        return [
            format_brand(b, translation=translations.get(b["id"]), lang=lang)
            for b in brands
        ]

    return [format_brand(b, lang=lang) for b in brands]


def fetch_brand_detail(brand_id: int, lang: str = "en"):
    raise NotImplementedError("Move /brands/{id} from legacy_main.py")


def get_categories():
    """
    TODO:
    copia qui il corpo della vecchia route GET /categories
    """
    raise NotImplementedError("Move /categories logic from legacy_main.py into get_categories()")


def get_public_sources_summary():
    """
    TODO:
    copia qui il corpo della vecchia route GET /sources/public
    """
    raise NotImplementedError("Move /sources/public logic from legacy_main.py into get_public_sources_summary()")
