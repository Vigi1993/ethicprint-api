from app.integrations.supabase_client import supabase


def fetch_scoring_criteria():
    res = (
        supabase.table("scoring_criteria")
        .select("*")
        .eq("active", True)
        .order("category_key")
        .order("sort_order")
        .execute()
    )

    data = res.data or []

    grouped = {}
    for c in data:
        key = c["category_key"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)

    return {"criteria": data, "grouped": grouped}
