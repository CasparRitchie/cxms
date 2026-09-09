"""Coverage accounting for the local FIS competition and result catalogue."""

import re
from collections import Counter
from datetime import date


COVERAGE_SCOPE_LABELS = {
    "full_classification": "Full classification",
    "official_top_10": "FIS historical top 10",
    "official_top_25": "FIS historical top 25",
    "unknown_partial": "Unknown/partial depth",
}


def result_coverage_scope(season_code, *, partial=False):
    """Describe the depth exposed by the official FIS result archive."""
    if partial:
        return "unknown_partial"
    try:
        season = int(season_code)
    except (TypeError, ValueError):
        return "unknown_partial"
    if 1967 <= season <= 1978:
        return "official_top_10"
    if 1979 <= season <= 1991:
        return "official_top_25"
    return "full_classification"


def coverage_scope_label(scope):
    return COVERAGE_SCOPE_LABELS.get(scope, COVERAGE_SCOPE_LABELS["unknown_partial"])


def coverage_percent(complete, total):
    if not total:
        return 0
    percentage = round((complete / total) * 100, 1)
    return 99.9 if complete < total and percentage == 100 else percentage


def competition_result_status(competition):
    """Return why a catalogue entry should or should not have classifications."""
    metadata = competition.get("metadata") or {}
    explicit = str(metadata.get("competition_kind") or "").casefold()
    status = str(metadata.get("race_status") or "").casefold()
    searchable = " ".join(str(value or "") for value in (
        competition.get("name"), metadata.get("event_code"), metadata.get("discipline"),
        " ".join(metadata.get("source_labels") or []),
    )).casefold()
    source_labels = {str(value or "").upper() for value in metadata.get("source_labels") or []}
    source_categories = source_labels & {"WC", "EC", "WSC", "OWG", "JUN", "FIS", "NC", "NAC", "SAC", "ANC", "CC"}
    if source_categories and "WC" not in source_categories:
        return "non_result"
    if explicit == "training" or re.search(r"\btraining\b", searchable):
        return "training"
    if explicit == "team_event" or re.search(r"\bteam\s*parallel\b|\bparallel\s*team\b|\bteam event\b", searchable):
        return "team_event"
    if status in {"cancelled", "deleted", "replaced"} or re.search(r"\b(cancelled|canceled|deleted|replaced by)\b", searchable):
        return status if status in {"cancelled", "deleted", "replaced"} else "cancelled"
    if metadata.get("is_result_expected") is False:
        return "non_result"
    return "result"


def build_result_coverage(competitions, imports, *, as_of=None, seasons=None):
    """Compare stored classifications with completed, catalogued competitions.

    This proves coverage of CXMS's current catalogue only. It deliberately does
    not claim that the catalogue itself contains every competition published by
    FIS.
    """
    cutoff = (as_of or date.today()).isoformat()
    wanted_seasons = {str(value) for value in (seasons or []) if str(value)}
    expected = {}
    catalogued_ids = set()
    excluded_ids = set()
    excluded = {"training": 0, "team_event": 0, "cancelled": 0, "deleted": 0, "replaced": 0, "non_result": 0}
    for competition in competitions:
        race_id = str(competition.get("canonical_id") or "")
        metadata = competition.get("metadata") or {}
        race_date = str(metadata.get("date") or "")
        season = str(metadata.get("season_code") or "")
        if (not race_id.isdigit() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", race_date)
                or race_date > cutoff or (wanted_seasons and season not in wanted_seasons)):
            continue
        catalogued_ids.add(race_id)
        result_status = competition_result_status(competition)
        if result_status != "result":
            excluded[result_status] = excluded.get(result_status, 0) + 1
            excluded_ids.add(race_id)
            continue
        expected[race_id] = competition

    imported = {
        str(item.get("race_id")): item for item in imports
        if not wanted_seasons or str(item.get("season_code") or "") in wanted_seasons
    }
    complete_ids = {race_id for race_id in expected if imported.get(race_id, {}).get("import_status") == "complete"}
    partial_ids = {race_id for race_id in expected if imported.get(race_id, {}).get("import_status") == "partial"}
    failed_ids = {race_id for race_id in expected if imported.get(race_id, {}).get("import_status") == "failed"}
    missing_ids = set(expected) - set(imported)
    total = len(expected)

    def scope_for(race_id):
        item = imported.get(race_id, {})
        return item.get("coverage_scope") or result_coverage_scope(
            item.get("season_code") or (expected.get(race_id, {}).get("metadata") or {}).get("season_code"),
            partial=item.get("import_status") == "partial",
        )

    scope_counts = Counter(scope_for(race_id) for race_id in complete_ids | partial_ids)

    by_season = []
    season_values = sorted({str((item.get("metadata") or {}).get("season_code") or "") for item in expected.values()}, reverse=True)
    for season in season_values:
        ids = {race_id for race_id, item in expected.items() if str((item.get("metadata") or {}).get("season_code") or "") == season}
        complete = len(ids & complete_ids)
        season_scopes = Counter(scope_for(race_id) for race_id in ids & (complete_ids | partial_ids))
        by_season.append({
            "season_code": season, "catalogued": len(ids), "complete": complete,
            "partial": len(ids & partial_ids), "failed": len(ids & failed_ids),
            "missing": len(ids & missing_ids),
            "coverage_percent": coverage_percent(complete, len(ids)),
            "coverage_scopes": dict(season_scopes),
            "coverage_scope_labels": [coverage_scope_label(scope) for scope in COVERAGE_SCOPE_LABELS if season_scopes.get(scope)],
        })

    return {
        "catalogued": total, "complete": len(complete_ids), "partial": len(partial_ids),
        "failed": len(failed_ids), "missing": len(missing_ids),
        "rows": sum(int(imported[race_id].get("row_count") or 0) for race_id in expected if race_id in imported),
        "coverage_percent": coverage_percent(len(complete_ids), total),
        "catalogue_coverage_complete": bool(total and not missing_ids and not partial_ids and not failed_ids),
        "external_catalogue_verified": False,
        "excluded": excluded, "excluded_total": sum(excluded.values()),
        "excluded_imports": len(set(imported) & excluded_ids),
        "orphaned_imports": len(set(imported) - catalogued_ids),
        "eligible_race_ids": sorted(expected, key=int),
        "missing_race_ids": sorted(missing_ids, key=int), "by_season": by_season,
        "coverage_scopes": {scope: scope_counts.get(scope, 0) for scope in COVERAGE_SCOPE_LABELS},
    }
