from fastapi import HTTPException

from app.integrations.supabase_client import supabase
from app.services.scoring import compute_brand_score_v2, detect_tier


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


async def approve_source_proposal(
    proposal_id: int,
    background_tasks,
    body=None,
    judgment_values=None,
    judgment_labels_it=None,
):
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

    tier = detect_tier(p.get("publisher", ""))

    new_source = (
        supabase.table("sources")
        .insert(
            {
                "brand_id": p["brand_id"],
                "category_key": p["category_key"],
                "url": p["url"],
                "title": p["title"],
                "publisher": p["publisher"],
                "broken": False,
                "content_missing": False,
                "tier": tier,
            }
        )
        .execute()
    )
    source_id = new_source.data[0]["id"] if new_source.data else None

    (
        supabase.table("source_proposals")
        .update(
            {
                "status": "approved",
                "ai_tier": tier,
            }
        )
        .eq("id", proposal_id)
        .execute()
    )

    if p.get("replaces_id"):
        supabase.table("sources").delete().eq("id", p["replaces_id"]).execute()

    judgment = (
        body.confirmed_judgment if body and body.confirmed_judgment else None
    ) or p.get("ai_judgment")

    if source_id and judgment and judgment_values and judgment in judgment_values:
        tier_values = {
            1: {20: 20, 10: 10, -10: -10, -20: -20},
            2: {20: 10, 10: 5, -10: -5, -20: -10},
            3: {20: 2, 10: 1, -10: -1, -20: -2},
        }

        base_val = judgment_values[judgment]
        value = tier_values.get(tier, tier_values[2]).get(base_val, base_val)

        criterion_code = p.get("ai_criterion", "")
        crit_res = None

        if criterion_code:
            crit_res = (
                supabase.table("scoring_criteria")
                .select("id")
                .eq("code", criterion_code)
                .limit(1)
                .execute()
            )

        if not crit_res or not crit_res.data:
            crit_res = (
                supabase.table("scoring_criteria")
                .select("id")
                .eq("category_key", p["category_key"])
                .eq("active", True)
                .order("sort_order")
                .limit(1)
                .execute()
            )

        if crit_res and crit_res.data:
            criterion_id = crit_res.data[0]["id"]
            label_it = judgment_labels_it.get(judgment, judgment) if judgment_labels_it else judgment

            try:
                supabase.table("criterion_source_scores").upsert(
                    {
                        "brand_id": p["brand_id"],
                        "criterion_id": criterion_id,
                        "source_id": source_id,
                        "tier": tier,
                        "value": value,
                        "label_en": judgment,
                        "label_it": label_it,
                        "notes": p.get("ai_rationale", ""),
                        "status": "draft",
                    },
                    on_conflict="brand_id,criterion_id,source_id",
                ).execute()

                background_tasks.add_task(compute_brand_score_v2, p["brand_id"])
            except Exception as e:
                print(f"criterion_source_scores upsert failed: {e}")

    return {
        "message": "Proposal approved.",
        "tier": tier,
        "judgment_saved": bool(judgment and judgment_values and judgment in judgment_values),
    }

def reject_source_proposal(proposal_id: int):
    (
        supabase.table("source_proposals")
        .update({"status": "rejected"})
        .eq("id", proposal_id)
        .execute()
    )
    return {"message": "Proposal rejected"}

def fetch_score_proposals(status: str = "pending"):
    res = (
        supabase.table("score_proposals")
        .select("*, brands(name), sources(url, title, publisher), scoring_criteria(label_en, label_it, code)")
        .eq("status", status)
        .order("created_at", desc=True)
        .execute()
    )

    return {
        "count": len(res.data or []),
        "proposals": res.data or [],
    }

def approve_score_proposal(proposal_id: int):
    prop_res = (
        supabase.table("score_proposals")
        .select("*")
        .eq("id", proposal_id)
        .single()
        .execute()
    )
    if not prop_res.data:
        raise HTTPException(status_code=404, detail="Proposal not found")

    p = prop_res.data
    criterion_id = p.get("criterion_id")
    if not criterion_id:
        raise HTTPException(status_code=400, detail="Proposal has no criterion_id")

    supabase.table("brand_scores").upsert(
        {
            "brand_id": p["brand_id"],
            "criterion_id": criterion_id,
            "score": p["proposed_score"],
            "label_en": p.get("proposed_label_en", ""),
            "label_it": p.get("proposed_label_it", ""),
            "notes": p.get("motivation", ""),
            "source_ids": [p["source_id"]] if p.get("source_id") else [],
            "status": "published",
            "last_updated": "now()",
        },
        on_conflict="brand_id,criterion_id",
    ).execute()

    criteria_res = (
        supabase.table("scoring_criteria")
        .select("id")
        .eq("category_key", p["category_key"])
        .eq("active", True)
        .execute()
    )
    criterion_ids = [c["id"] for c in (criteria_res.data or [])]

    scores_res = (
        supabase.table("brand_scores")
        .select("score")
        .eq("brand_id", p["brand_id"])
        .eq("status", "published")
        .in_("criterion_id", criterion_ids)
        .execute()
    )
    scores = [row["score"] for row in (scores_res.data or [])]

    if scores:
        avg = sum(scores) / len(scores)
        category_score = round((avg - 1) / 4 * 25)
    else:
        category_score = 13

    col = f"score_{p['category_key']}"
    (
        supabase.table("brands")
        .update({col: category_score, "last_updated": "now()"})
        .eq("id", p["brand_id"])
        .execute()
    )

    (
        supabase.table("score_proposals")
        .update({"status": "approved"})
        .eq("id", proposal_id)
        .execute()
    )

    return {
        "message": "Score updated",
        "category": p["category_key"],
        "category_score": category_score,
    }
