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
