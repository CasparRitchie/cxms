"""Orchestrates detectors while keeping calculations and wording inspectable."""

from collections import defaultdict

from .context import InsightContext
from .detectors import (
    DETECTORS, career_totals, conditional_scenarios, milestones, streaks,
)
from .scoring import score_insight


CATEGORY_LABELS = {
    "career": "Career totals", "streak": "Streaks", "milestone": "Milestones",
    "venue": "Venue records", "margin": "Time and margins", "drought": "Droughts and gaps",
    "recent_form": "Recent form", "nation": "Nation patterns", "age": "Age records",
}


def _priority(score):
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Supporting"


def _deduplicate(insights):
    """Keep the strongest expression of the same subject/metric/condition."""
    selected = {}
    for insight in insights:
        key = (
            insight.subject_id, insight.category, insight.metric.get("name"),
            (insight.condition or {}).get("type"), insight.scope.get("venue"),
            tuple(insight.scope.get("disciplines") or ()),
        )
        existing = selected.get(key)
        if existing is None or insight.editorial_score > existing.editorial_score or (
                insight.editorial_score == existing.editorial_score and insight.id < existing.id):
            selected[key] = insight
    return list(selected.values())


def _group(items, category=""):
    grouped = defaultdict(list)
    for insight in items:
        if category and insight.category != category:
            continue
        item = insight.to_dict()
        item["priority_label"] = _priority(insight.editorial_score)
        grouped[insight.category].append(item)
    result = []
    for key in CATEGORY_LABELS:
        if category and key != category:
            continue
        values = sorted(grouped.get(key, []), key=lambda item: (-item["editorial_score"], item["id"]))[:6]
        if values:
            result.append({"category": key, "label": CATEGORY_LABELS[key], "items": values})
    return result


def build_engine_result(rows, *, coverage=None, scenario_athlete_ids=None,
                        category="", country_mapping=None, score_threshold=28):
    ctx = InsightContext(rows, coverage=coverage, country_mapping=country_mapping)
    profiles, career_insights = career_totals(ctx)
    streak_table, streak_insights = streaks(ctx)
    all_insights = [*career_insights, *streak_insights, *milestones(ctx, profiles)]
    for detector in DETECTORS:
        all_insights.extend(detector(ctx, profiles) if detector.__name__ == "venue_records" else detector(ctx))
    all_insights.extend(conditional_scenarios(ctx, profiles, scenario_athlete_ids))
    for insight in all_insights:
        score_insight(insight, coverage_complete=ctx.coverage["is_known_complete"])
    all_insights = _deduplicate(all_insights)
    visible = [item for item in all_insights if item.editorial_score >= score_threshold or item.status == "conditional"]
    visible.sort(key=lambda item: (-item.editorial_score, item.id))
    confirmed = [item for item in visible if item.status != "conditional"]
    scenarios = [item for item in visible if item.status == "conditional"]
    leader_rows = [{key: value for key, value in profile.items() if key != "rows"} for profile in profiles]
    return {
        "context": ctx, "profiles": profiles, "leaders": leader_rows, "streaks": streak_table,
        "structured_insights": [item.to_dict() for item in visible],
        "confirmed_groups": _group(confirmed, category), "scenario_groups": _group(scenarios, category),
        "coverage": ctx.coverage, "available_categories": [
            {"value": key, "label": label} for key, label in CATEGORY_LABELS.items()
            if any(item.category == key for item in visible)
        ],
        "score_threshold": score_threshold, "data_as_of": ctx.data_as_of,
    }
