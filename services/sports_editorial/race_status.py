from copy import deepcopy


def effective_race_status(competition):
    metadata = competition.get("metadata") or {}
    manual = str(metadata.get("manual_race_status") or "").lower()
    official = str(metadata.get("race_status") or "").lower()
    if official == "cancelled":
        return "cancelled", "fis"
    if manual == "cancelled":
        return "cancelled", "manual"
    if manual == "scheduled":
        return "scheduled", "manual"
    return "scheduled", "fis" if official else "catalogue"


def matching_competitions(submission, competitions):
    event_ids = {str(value) for value in submission.get("fis_event_ids") or []}
    stored_race_ids = {str(value) for value in submission.get("fis_race_ids") or []}
    event_codes = {str(value).upper() for value in submission.get("fis_event_discipline_codes") or [] if value}
    if not event_codes and submission.get("fis_event_discipline_code"):
        event_codes.add(str(submission["fis_event_discipline_code"]).upper())
    genders = {str(value).upper() for value in submission.get("genders") or [] if value}
    if not genders and submission.get("gender"):
        genders.add(str(submission["gender"]).upper())
    race_date = str(submission.get("event_date") or "")[:10]
    # A single Event/Gender selection describes one race and can be narrowed by
    # Race Date. Multi-select sheets intentionally cover several races, which
    # can take place on different dates within the same FIS event.
    use_race_date = bool(race_date and len(event_codes) <= 1 and len(genders) <= 1)
    matches = []
    for competition in competitions:
        metadata = competition.get("metadata") or {}
        race_id = str(competition.get("canonical_id") or "")
        if stored_race_ids:
            if race_id in stored_race_ids:
                matches.append(competition)
            continue
        if str(metadata.get("event_id") or "") not in event_ids:
            continue
        if str(metadata.get("competition_kind") or "race").casefold() == "training":
            continue
        if event_codes and str(metadata.get("event_code") or "").upper() not in event_codes:
            continue
        if genders and str(metadata.get("gender") or "").upper() not in genders:
            continue
        if use_race_date and str(metadata.get("date") or "")[:10] != race_date:
            continue
        matches.append(competition)
    return matches


def race_alerts(submission, competitions):
    alerts = []
    for competition in matching_competitions(submission, competitions):
        status, source = effective_race_status(competition)
        if status != "cancelled":
            continue
        metadata = competition.get("metadata") or {}
        alerts.append({
            "race_id": str(competition.get("canonical_id") or ""),
            "codex": str(metadata.get("codex") or ""),
            "name": competition.get("name") or "FIS race",
            "source": source,
            "official_comment": metadata.get("official_status_comment") or metadata.get("web_comment"),
        })
    return alerts


def decorate_submission_race_status(submission, competitions):
    item = deepcopy(submission)
    linked_races = []
    for competition in matching_competitions(item, competitions):
        linked = deepcopy(competition)
        linked["effective_race_status"], linked["effective_race_status_source"] = effective_race_status(competition)
        linked_races.append(linked)
    linked_races.sort(key=lambda race: (
        str((race.get("metadata") or {}).get("date") or ""),
        str((race.get("metadata") or {}).get("event_code") or ""),
        str((race.get("metadata") or {}).get("gender") or ""),
        str(race.get("canonical_id") or ""),
    ))
    item["linked_fis_races"] = linked_races
    item["linked_fis_race_count"] = len(linked_races)
    item["cancelled_fis_race_count"] = sum(race["effective_race_status"] == "cancelled" for race in linked_races)
    if item["cancelled_fis_race_count"] == 0:
        item["linked_fis_race_status"] = "scheduled" if linked_races else "unlinked"
    elif item["cancelled_fis_race_count"] == len(linked_races):
        item["linked_fis_race_status"] = "cancelled"
    else:
        item["linked_fis_race_status"] = "partially_cancelled"
    alerts = race_alerts(item, linked_races)
    item["race_alerts"] = alerts
    if alerts:
        item["race_status"] = "cancelled"
        item["race_status_source"] = "fis" if any(alert["source"] == "fis" for alert in alerts) else "manual"
    return item


def decorate_submission_fis_schedule(submission, events, competitions):
    """Attach the read-only FIS event schedule and linked race details."""
    item = decorate_submission_race_status(submission, competitions)
    wanted_event_ids = {str(value) for value in item.get("fis_event_ids") or []}
    linked_events = [
        deepcopy(event) for event in events
        if str(event.get("canonical_id") or "") in wanted_event_ids
    ]
    linked_events.sort(key=lambda event: (
        str((event.get("metadata") or {}).get("start_date") or ""),
        str(event.get("canonical_id") or ""),
    ))
    item["linked_fis_events"] = linked_events
    item["linked_fis_event_count"] = len(linked_events)
    return item
