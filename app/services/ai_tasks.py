from app.core.config import settings
from app.integrations.supabase_client import supabase

async def generate_impact_summary(brand_id: int, brand: dict, criterion_scores: list = None) -> dict:
    if not ANTHROPIC_KEY:
        return {}
    import httpx as _httpx
    name = brand.get("name", "")
    sector = (brand.get("sectors") or {}).get("label_en", "")
    total_score = brand.get("total_score_v2")
    criteria_published = brand.get("criteria_published", 0) or 0
    if total_score is None or criteria_published == 0:
        return {}
    verdict = get_verdict(total_score)
    band = verdict["band"]
    notes = {
        "armi":     brand.get("note_armi", "") or "",
        "ambiente": brand.get("note_ambiente", "") or "",
        "diritti":  brand.get("note_diritti", "") or "",
        "fisco":    brand.get("note_fisco", "") or "",
    }
    notes_text = "\n".join([f"- {cat}: {notes[cat]}" for cat in CATS if notes[cat]])
    criteria_text = ""
    if criterion_scores:
        lines = []
        for c in criterion_scores:
            if c.get("criteria_met") and c.get("computed_score") is not None:
                label = (c.get("criterion") or {}).get("label_en", f"criterion {c.get('criterion_id')}")
                score = c.get("computed_score")
                lines.append(f"  - {label}: {'+' if score > 0 else ''}{score}/20")
        if lines:
            criteria_text = "Criteria scores (−20 to +20):\n" + "\n".join(lines)
    prompt = f"""You are writing a concise ethical impact summary for EthicPrint, a brand ethics scoring tool.

Brand: {name}
Sector: {sector}
Overall score: {total_score} out of ±400 → verdict: {band}
Criteria with published scores: {criteria_published}/20

{criteria_text}

{("Notes:\n" + notes_text) if notes_text else ""}

Write TWO short sentences (max 35 words each) that tell a consumer the CONCRETE ethical impact of choosing or avoiding this brand.
Be specific, factual, and direct. No marketing language. Focus on the strongest signal in the data.

Return ONLY valid JSON:
{{"en": "English sentence here.", "it": "Frase italiana qui."}}"""
    try:
        async with _httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            text = r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            result = __import__("json").loads(text)
            en = result.get("en", "")
            it = result.get("it", "")
            if en and it:
                supabase.table("brands").update({
                    "impact_summary_en": en,
                    "impact_summary_it": it,
                }).eq("id", brand_id).execute()
            return {"en": en, "it": it}
    except Exception as e:
        print(f"generate_impact_summary error: {e}")
        return {}
