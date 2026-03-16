import json
import os
from datetime import datetime

import httpx

from fastapi import HTTPException

from app.core.config import settings
from app.integrations.supabase_client import supabase


CAT_LABELS = {
    "armi": "arms weapons military contracts defense",
    "ambiente": "environment CO2 emissions climate sustainability",
    "diritti": "human rights labor rights workers conditions supply chain",
    "fisco": "tax avoidance tax haven fiscal transparency",
}


async def find_source_replacement(source_id: int):
    source_res = (
        supabase.table("sources")
        .select("*, brands(name)")
        .eq("id", source_id)
        .single()
        .execute()
    )
    if not source_res.data:
        raise HTTPException(status_code=404, detail="Source not found")

    source = source_res.data
    brand_name = (source.get("brands") or {}).get("name", "")
    category_key = source.get("category_key", "")
    cat_desc = CAT_LABELS.get(category_key, category_key)

    year = datetime.now().year
    query = f"{brand_name} {cat_desc} {year-1}..{year}"

    brave_key = os.getenv("BRAVE_API_KEY")
    candidates = []

    if brave_key:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": brave_key,
                    },
                    params={
                        "q": query,
                        "count": 8,
                        "search_lang": "en",
                        "freshness": "py",
                    },
                    timeout=10,
                )
                results = r.json().get("web", {}).get("results", [])
                candidates = [
                    {
                        "url": x.get("url"),
                        "title": x.get("title"),
                        "description": x.get("description", ""),
                    }
                    for x in results
                    if x.get("url")
                ]
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Brave search failed: {e}")

    if not candidates:
        return {"candidates": [], "query": query}

    existing_urls = {
        s["url"] for s in (supabase.table("sources").select("url").execute().data or [])
    }
    candidates = [c for c in candidates if c["url"] not in existing_urls]

    approved = []
    if settings.ANTHROPIC_API_KEY:
        async with httpx.AsyncClient() as c:
            for candidate in candidates[:6]:
                prompt = f"""You are evaluating a replacement source for EthicPrint.

Brand: {brand_name}
Category: {category_key} ({cat_desc})
Original broken source: {source.get('url', '')}

Candidate:
- URL: {candidate.get('url', '')}
- Title: {candidate.get('title', '')}
- Description: {candidate.get('description', '')}

Is this a relevant, credible replacement? Reply ONLY with JSON:
{{"relevant": true/false, "publisher": "name", "summary": "1 sentence", "tier": 1/2/3}}"""

                try:
                    r = await c.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "Content-Type": "application/json",
                            "x-api-key": settings.ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01",
                        },
                        json={
                            "model": "claude-haiku-4-5-20251001",
                            "max_tokens": 200,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=30,
                    )
                    text = (
                        r.json()["content"][0]["text"]
                        .strip()
                        .replace("```json", "")
                        .replace("```", "")
                        .strip()
                    )
                    ev = json.loads(text)

                    if ev.get("relevant"):
                        approved.append(
                            {
                                **candidate,
                                "publisher": ev.get("publisher", ""),
                                "summary": ev.get("summary", ""),
                                "tier": ev.get("tier", 3),
                            }
                        )

                    if len(approved) >= 3:
                        break
                except Exception:
                    continue

    return {
        "source_id": source_id,
        "brand_name": brand_name,
        "category_key": category_key,
        "query": query,
        "candidates": approved,
    }

def create_replacement_proposal(source_id: int, data: dict):
    source_res = (
        supabase.table("sources")
        .select("brand_id, category_key")
        .eq("id", source_id)
        .single()
        .execute()
    )
    if not source_res.data:
        raise HTTPException(status_code=404, detail="Source not found")

    s = source_res.data

    try:
        res = (
            supabase.table("source_proposals")
            .insert(
                {
                    "brand_id": s["brand_id"],
                    "category_key": s["category_key"],
                    "url": data.get("url"),
                    "title": data.get("title"),
                    "publisher": data.get("publisher", ""),
                    "summary": data.get("summary", ""),
                    "status": "pending",
                    "job_type": "replacement",
                    "replaces_id": source_id,
                }
            )
            .execute()
        )

        return {"ok": True, "id": res.data[0]["id"] if res.data else None}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def mark_source_resolved(source_id: int):
    supabase.table("sources").update(
        {"broken": False, "content_missing": False}
    ).eq("id", source_id).execute()

    return {"ok": True}

def exclude_source_from_criterion(source_id: int, data):
    """Esclude una fonte da un criterio specifico senza rimuoverla dalle altre."""
    try:
        supabase.table("source_criterion_exclusions").upsert(
            {
                "brand_id": data.brand_id,
                "source_id": source_id,
                "criterion_id": data.criterion_id,
            },
            on_conflict="brand_id,source_id,criterion_id",
        ).execute()

        return {"ok": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def remove_source_exclusion(source_id: int, criterion_id: int, brand_id: int):
    """Rimuove l'esclusione di una fonte da un criterio."""
    try:
        (
            supabase.table("source_criterion_exclusions")
            .delete()
            .eq("source_id", source_id)
            .eq("criterion_id", criterion_id)
            .eq("brand_id", brand_id)
            .execute()
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
