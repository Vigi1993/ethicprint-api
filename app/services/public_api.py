from app.integrations.supabase_client import supabase


def get_brands(lang: str = "en"):
    """
    TODO:
    copia qui il corpo della vecchia route GET /brands da legacy_main.py
    mantenendo identica la shape del JSON restituito al frontend.
    """
    raise NotImplementedError("Move /brands logic from legacy_main.py into get_brands()")


def get_brand_detail(brand_id: int, lang: str = "en"):
    """
    TODO:
    copia qui il corpo della vecchia route GET /brands/{id}
    """
    raise NotImplementedError("Move /brands/{id} logic from legacy_main.py into get_brand_detail()")


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
