JUDGMENT_VALUES = {
    "positive": 20,
    "prev_positive": 10,
    "prev_negative": -10,
    "negative": -20,
}

JUDGMENT_LABELS_IT = {
    "positive": "Positiva",
    "prev_positive": "Prevalentemente positiva",
    "prev_negative": "Prevalentemente negativa",
    "negative": "Negativa",
}

from typing import Optional

PUBLIC_SCORE_LABELS_EN = [
    (24, "Ethically Compromised"),
    (44, "Scarcely Ethical"),
    (54, "Partially Ethical"),
    (74, "Fairly Ethical"),
    (100, "Deeply Ethical"),
]

PUBLIC_SCORE_LABELS_IT = [
    (24, "Eticamente Inadeguato"),
    (44, "Scarsamente Etico"),
    (54, "Parzialmente Etico"),
    (74, "Abbastanza Etico"),
    (100, "Profondamente Etico"),
]


def raw_score_to_public_score(raw_score: Optional[float]) -> Optional[int]:
    if raw_score is None:
        return None

    clamped = max(-400, min(400, raw_score))
    return round(((clamped + 400) / 800) * 100)


def public_score_label(score: Optional[int], lang: str = "en") -> str:
    if score is None:
      return "Dati insufficienti" if lang == "it" else "Insufficient data"

    labels = PUBLIC_SCORE_LABELS_IT if lang == "it" else PUBLIC_SCORE_LABELS_EN

    for upper_bound, label in labels:
        if score <= upper_bound:
            return label

    return labels[-1][1]
