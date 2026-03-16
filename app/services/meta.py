from app.integrations.supabase_client import supabase
from app.core.constants import DEFAULT_LANG, SUPPORTED_LANGS


def fetch_sectors():
    res = (
        supabase.table("sectors")
        .select("*")
        .eq("active", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []


def fetch_langs():
    return {
        "default": DEFAULT_LANG,
        "supported": SUPPORTED_LANGS,
        "labels": {
            "en": "English",
            "it": "Italiano",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
        },
    }


def fetch_publishers():
    res = (
        supabase.table("publishers")
        .select("id, name, url, tier, topic")
        .eq("active", True)
        .order("tier")
        .order("name")
        .execute()
    )

    data = res.data or []

    return {
        "total": len(data),
        "tier1": [p for p in data if p["tier"] == 1],
        "tier2": [p for p in data if p["tier"] == 2],
        "tier3": [p for p in data if p["tier"] == 3],
    }
