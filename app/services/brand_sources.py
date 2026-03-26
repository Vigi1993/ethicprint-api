from fastapi import HTTPException

from app.integrations.supabase_client import supabase


def fetch_brand_sources(brand_id: int):
    """
    Ritorna tutte le fonti del brand come array flat.
    Include esclusioni per criterio e proposal_id per ogni fonte.
    """
    brand_res = (
        supabase.table("brands")
        .select("id")
        .eq("id", brand_id)
        .single()
        .execute()
    )
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    res = (
        supabase.table("sources")
        .select("id, url, title, publisher, published_at, category_key, tier")
        .eq("brand_id", brand_id)
        .neq("broken", True)
        .neq("content_missing", True)
        .order("category_key")
        .execute()
    )

    excl_res = (
        supabase.table("source_criterion_exclusions")
        .select("source_id, criterion_id")
        .eq("brand_id", brand_id)
        .execute()
    )
    excl_map: dict = {}
    for e in (excl_res.data or []):
        sid = e["source_id"]
        if sid not in excl_map:
            excl_map[sid] = []
        excl_map[sid].append(e["criterion_id"])

    props_res = (
        supabase.table("source_proposals")
        .select("id, url")
        .eq("brand_id", brand_id)
        .eq("status", "approved")
        .execute()
    )
    proposal_by_url = {p["url"]: p["id"] for p in (props_res.data or [])}

    sources = []
    for s in (res.data or []):
        sources.append(
            {
                "id": s["id"],
                "url": s["url"],
                "title": s["title"],
                "publisher": s["publisher"],
                "published_at": s["published_at"],
                "category_key": s["category_key"],
                "tier": s.get("tier", 3),
                "excluded_from_criteria": excl_map.get(s["id"], []),
                "proposal_id": proposal_by_url.get(s["url"]),
            }
        )

    return {"sources": sources}
