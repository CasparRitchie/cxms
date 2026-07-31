"""Deterministic, explainable editorial-interest scoring."""


CATEGORY_RARITY = {
    "record": 20, "milestone": 17, "streak": 15, "margin": 14,
    "venue": 13, "nation": 12, "age": 12, "drought": 11,
    "recent_form": 8, "career": 6,
}


def score_insight(insight, coverage_complete=False, duplicate_penalty=0):
    metric_value = insight.metric.get("value")
    magnitude = min(12, int(metric_value)) if isinstance(metric_value, (int, float)) and metric_value > 0 else 4
    breakdown = {
        "rarity": CATEGORY_RARITY.get(insight.category, 8),
        "race_relevance": 18 if insight.condition else (12 if insight.scope.get("venue") else 7),
        "historical_significance": 15 if insight.category in {"record", "venue", "age", "margin"} else 7,
        "milestone": 16 if insight.category == "milestone" else 0,
        "recent_form": 9 if insight.category in {"streak", "recent_form", "drought"} else 0,
        "magnitude": magnitude,
        "confidence": round(10 * insight.confidence),
        "coverage_penalty": 0 if coverage_complete else -8,
        "duplication_penalty": -abs(int(duplicate_penalty)),
        "triviality_penalty": -8 if magnitude <= 1 and insight.category not in {"milestone", "record"} else 0,
    }
    insight.score_breakdown = breakdown
    insight.editorial_score = max(0, min(100, sum(breakdown.values())))
    return insight
