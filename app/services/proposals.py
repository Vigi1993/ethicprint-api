from fastapi import HTTPException

from app.integrations.supabase_client import supabase
from app.services.scoring import compute_brand_score_v2


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


def revert_source_proposal_to_pending(proposal_id: int):
    """
    Riporta una proposta approved o rejected a stato pending.
    Se era approved, rimuove anche la fonte da sources.
    """
    prop_res = (
        supabase.table("source_proposals")
        .select("*")
        .eq("id", proposal_id)
        .single()
        .execute()
    )
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")

    p = prop_res.data

    if p["status"] == "approved":
        src_res = (
            supabase.table("sources")
            .select("id")
            .eq("brand_id", p["brand_id"])
            .eq("url", p["url"])
            .execute()
        )
        if src_res.data:
            source_id = src_res.data[0]["id"]

            (
                supabase.table("criterion_source_scores")
                .delete()
                .eq("source_id", source_id)
                .execute()
            )

            (
                supabase.table("source_criterion_exclusions")
                .delete()
                .eq("source_id", source_id)
                .execute()
            )

            supabase.table("sources").delete().eq("id", source_id).execute()

            try:
                compute_brand_score_v2(p["brand_id"])
            except Exception:
                pass

    (
        supabase.table("source_proposals")
        .update({"status": "pending"})
        .eq("id", proposal_id)
        .execute()
    )

    return {"ok": True, "message": "Proposal reverted to pending"}
