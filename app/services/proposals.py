from app.integrations.supabase_client import supabase


def fetch_source_proposals(status: str = "pending"):
    res = (
        supabase.table("source_proposals")
        .select("*, brands(name)")
        .eq("status", status)
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "count": len(res.data or []),
        "proposals": res.data or [],
    }
