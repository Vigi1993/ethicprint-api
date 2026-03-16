import json

import httpx

from app.core.constants import DEFAULT_LANG
from app.core.config import settings
from app.integrations.supabase_client import supabase


def get_translation(brand_id: int, lang: str) -> dict | None:
    if lang == DEFAULT_LANG:
        return None

    try:
        res = (
            supabase.table("brand_translations")
            .select("*")
            .eq("brand_id", brand_id)
            .eq("lang", lang)
            .limit(1)
            .execute()
        )

        if res.data and len(res.data) > 0:
            return res.data[0]

        return None

    except Exception as e:
        print(f"get_translation error brand_id={brand_id} lang={lang}: {e}")
        return None


async def generate_and_save_translation(brand_id: int, brand: dict, lang: str):
    if not settings.ANTHROPIC_API_KEY:
        return

    lang_names = {
        "it": "Italian",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
    }
    lang_name = lang_names.get(lang, lang)

    prompt = f"""Translate the following ethical brand assessment notes from English to {lang_name}.
Return ONLY a valid JSON object with these exact keys: note_armi, note_ambiente, note_diritti, note_fisco.
Keep the tone factual and neutral. Do not add or remove information.

Brand: {brand["name"]}

note_armi: {brand["note_armi"]}
note_ambiente: {brand["note_ambiente"]}
note_diritti: {brand["note_diritti"]}
note_fisco: {brand["note_fisco"]}
"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )

            data = response.json()
            text = data["content"][0]["text"].strip()

            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            translated = json.loads(text.strip())

        supabase.table("brand_translations").upsert(
            {
                "brand_id": brand_id,
                "lang": lang,
                "note_armi": translated.get("note_armi"),
                "note_ambiente": translated.get("note_ambiente"),
                "note_diritti": translated.get("note_diritti"),
                "note_fisco": translated.get("note_fisco"),
            },
            on_conflict="brand_id,lang",
        ).execute()

    except Exception as e:
        print(f"Translation error for brand {brand_id} lang {lang}: {e}")
