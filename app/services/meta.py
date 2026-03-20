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

        print("DEBUG rows:", len(res.data or []), res.data)

        results = []
        for row in res.data or []:
            print("DEBUG row:", row)

            brand_res = supabase.table("brands").select("id, name").eq("id", row["brand_id"]).single().execute()
            print("DEBUG brand:", brand_res.data)

            source_res = supabase.table("sources").select("id, url, title, publisher").eq("id", row["source_id"]).single().execute()
            print("DEBUG source:", source_res.data)

            criterion_res = supabase.table("criteria").select("id, category_key").eq("id", row["criterion_id"]).single().execute()
            print("DEBUG criterion:", criterion_res.data)

            if not brand_res.data or not source_res.data:
                print("DEBUG skipped — missing brand or source")
                continue

            results.append({
                "brand_id": brand_res.data.get("id"),
                "brand_name": brand_res.data.get("name", ""),
                "category_key": criterion_res.data.get("category_key", "") if criterion_res.data else "",
                "value": row.get("value"),
                "judgment": row.get("judgment", ""),
                "label_en": row.get("label_en", ""),
                "label_it": row.get("label_it", ""),
                "source_id": source_res.data.get("id"),
                "title": source_res.data.get("title", ""),
                "publisher": source_res.data.get("publisher", ""),
                "url": source_res.data.get("url", ""),
                "created_at": row.get("created_at"),
            })

        print("DEBUG results:", results)
        return results

    except Exception as e:
        print(f"get_recent_source_updates error: {e}")
        return []
