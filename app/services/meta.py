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

def get_recent_source_updates(limit: int = 20) -> list[dict]:
    try:
        res = (
            supabase.table("criterion_source_scores")
            .select("*")
            .eq("status", "published")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        results = []
        for row in res.data or []:
            # fetch brand
            brand_res = supabase.table("brands").select("id, name").eq("id", row["brand_id"]).single().execute()
            brand = brand_res.data or {}

            # fetch source
            source_res = supabase.table("sources").select("id, url, title, publisher").eq("id", row["source_id"]).single().execute()
            source = source_res.data or {}

            # fetch criterion
            criterion_res = supabase.table("criteria").select("id, category_key").eq("id", row["criterion_id"]).single().execute()
            criterion = criterion_res.data or {}

            if not brand or not source:
                continue

            results.append({
                "brand_id": brand.get("id"),
                "brand_name": brand.get("name", ""),
                "category_key": criterion.get("category_key", ""),
                "value": row.get("value"),
                "judgment": row.get("judgment") if "judgment" in row else "",
                "label_en": row.get("label_en", ""),
                "label_it": row.get("label_it", ""),
                "source_id": source.get("id"),
                "title": source.get("title", ""),
                "publisher": source.get("publisher", ""),
                "url": source.get("url", ""),
                "created_at": row.get("created_at"),
            })

        return results

    except Exception as e:
        print(f"get_recent_source_updates error: {e}")
        return []
