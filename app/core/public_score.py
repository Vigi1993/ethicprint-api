from typing import Optional

def raw_score_to_public_score(raw_score: Optional[float]) -> Optional[int]:
    if raw_score is None:
        return None

    clamped = max(-400, min(400, raw_score))
    return round(((clamped + 400) / 800) * 100)


def public_score_label(score: Optional[int], lang: str = "en") -> str:
    if score is None:
        return "Dati insufficienti" if lang == "it" else "Insufficient data"

    if score <= 19:
        return "Critico" if lang == "it" else "Critical"
    if score <= 39:
        return "Problematico" if lang == "it" else "Problematic"
    if score <= 59:
        return "Controverso" if lang == "it" else "Controversial"
    if score <= 79:
        return "Positivo" if lang == "it" else "Positive"
    return "Virtuoso" if lang == "it" else "Virtuous"
