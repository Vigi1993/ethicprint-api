def smart_alternatives(brand_id: int, sector_id: int, lang: str, top_n: int = 3) -> list:
    res = supabase.table("brands") \
        .select("id, name, logo, total_score_v2, criteria_published, sectors(key, label, label_en, icon)") \
        .eq("sector_id", sector_id).neq("id", brand_id).not_.is_("total_score_v2", "null").execute()
    brands = res.data or []
    current_res = supabase.table("brands").select("total_score_v2").eq("id", brand_id).limit(1).execute()
    current_score = None
    if current_res.data:
        current_score = current_res.data[0].get("total_score_v2")
    if current_score is not None:
        better = [b for b in brands if (b.get("total_score_v2") or -400) > current_score]
    else:
        better = brands
    brands_sorted = sorted(better, key=lambda b: b.get("total_score_v2") or -400, reverse=True)[:top_n]
    result = []
    for b in brands_sorted:
        sector = b.get("sectors") or {}
        sector_label = sector.get("label_en", "") if lang == "en" and sector.get("label_en") else sector.get("label", "")
        result.append({
            "id": b["id"], "name": b["name"], "logo": b["logo"],
            "score": b.get("total_score_v2"), "criteria_published": b.get("criteria_published", 0),
            "sector": sector_label,
        })
    return result
