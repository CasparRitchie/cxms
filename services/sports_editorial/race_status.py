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
        if event_codes and str(metadata.get("event_code") or "").upper() not in event_codes:
            continue
        if genders and str(metadata.get("gender") or "").upper() not in genders:
            continue
        if race_date and str(metadata.get("date") or "")[:10] != race_date:
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
    alerts = race_alerts(item, competitions)
    item["race_alerts"] = alerts
    if alerts:
        item["race_status"] = "cancelled"
        item["race_status_source"] = "fis" if any(alert["source"] == "fis" for alert in alerts) else "manual"
    return item
