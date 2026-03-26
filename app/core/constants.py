TIER_VALUES = {
    1: {"positive": 20, "prev_positive": 10, "prev_negative": -10, "negative": -20},
    2: {"positive": 10, "prev_positive": 5, "prev_negative": -5, "negative": -10},
    3: {"positive": 2, "prev_positive": 1, "prev_negative": -1, "negative": -2},
}

SCORE_LABELS = {
    "positive": {"en": "Positive evidence", "it": "Evidenza positiva"},
    "prev_positive": {"en": "Predominantly positive", "it": "Prevalentemente positiva"},
    "prev_negative": {"en": "Predominantly negative", "it": "Prevalentemente negativa"},
    "negative": {"en": "Negative evidence", "it": "Evidenza negativa"},
}

FRESHNESS_MONTHS = 18
SCORE_RANGE = 400
CATS = ["armi", "ambiente", "diritti", "fisco"]

VERDICTS = [
    (200, 400, "Deeply Ethical", "Profondamente Etico", ""),
    (50, 199, "Fairly Ethical", "Abbastanza Etico", "✅"),
    (-49, 49, "Partially Ethical", "Parzialmente Etico", "⚖️"),
    (-199, -50, "Scarcely Ethical", "Scarsamente Etico", "⚠️"),
    (-400, -200, "Ethically Compromised", "Eticamente Inadeguato", ""),
]

TIER_WEIGHTS = {1: 3, 2: 2, 3: 1}
MIN_SOURCES_PER_CAT = 2
SUPPORTED_LANGS = ["en", "it", "es", "fr", "de"]
DEFAULT_LANG = "en"
