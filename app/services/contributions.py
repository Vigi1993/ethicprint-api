from fastapi import HTTPException

from app.integrations.supabase_client import supabase
from legacy_main import notify_contribution


async def create_brand_proposal(data, background_tasks):
    if not data.name or len(data.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Brand name too short")

    try:
        res = (
            supabase.table("brand_proposals")
            .insert(
                {
                    "name": data.name.strip(),
                    "sector_key": data.sector_key,
                    "website": data.website,
                    "reason": data.reason,
                    "submitter": data.submitter,
                    "status": "pending",
                }
            )
            .execute()
        )

        new_id = res.data[0]["id"] if res.data else None

        background_tasks.add_task(
            notify_contribution,
            "brand",
            {
                "Brand": data.name.strip(),
                "Sector": data.sector_key or "—",
                "Website": data.website or "—",
                "Reason": data.reason or "—",
                "Submitted by": data.submitter or "anonymous",
            },
        )

        return {"ok": True, "id": new_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def create_source_proposal(data, background_tasks):
    if not data.url or not data.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    brand_res = (
        supabase.table("brands")
        .select("id, name")
        .eq("id", data.brand_id)
        .limit(1)
        .execute()
    )
    if not brand_res.data:
        raise HTTPException(status_code=404, detail="Brand not found")

    brand_name = brand_res.data[0].get("name", str(data.brand_id))

    existing = supabase.table("sources").select("id").eq("url", data.url).execute()
    existing_prop = (
        supabase.table("source_proposals")
        .select("id")
        .eq("url", data.url)
        .execute()
    )

    if existing.data or existing_prop.data:
        raise HTTPException(status_code=409, detail="Source already exists or proposed")

    try:
        res = (
            supabase.table("source_proposals")
            .insert(
                {
                    "brand_id": data.brand_id,
                    "category_key": data.category_key,
                    "url": data.url,
                    "title": data.title,
                    "publisher": data.publisher or "",
                    "summary": data.summary or "",
                    "status": "pending",
                    "job_type": "new",
                }
            )
            .execute()
        )

        new_id = res.data[0]["id"] if res.data else None

        background_tasks.add_task(
            notify_contribution,
            "source",
            {
                "Brand": brand_name,
                "Category": data.category_key or "—",
                "URL": data.url,
                "Title": data.title or "—",
                "Publisher": data.publisher or "—",
                "Submitted by": data.submitter or "anonymous",
            },
        )

        return {"ok": True, "id": new_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
