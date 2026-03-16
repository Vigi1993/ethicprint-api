from app.integrations.supabase_client import supabase


def fetch_sectors():
    res = (
        supabase.table("sectors")
        .select("*")
        .eq("active", True)
        .order("sort_order")
        .execute()
    )

    return res.data or []
