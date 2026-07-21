from .formatting import rich_text_to_plain


FIS_LINK_TYPES = {"athlete": "athlete", "country": "nation", "event": "event", "competition": "competition"}
PILOT_METADATA_FIELDS = {
    "athlete": ("competitor_id", "gender", "birthdate", "status"),
    "country": (),
    "event": ("season_code", "discipline_code", "category_code"),
    "competition": ("event_id", "codex", "gender", "date", "discipline_code"),
}


def _export_entity(entity):
    entity_type = entity["entity_type"]
    canonical_id = str(entity.get("canonical_id") or entity["id"])
    metadata = entity.get("metadata") or {}
    details = {field: metadata[field] for field in PILOT_METADATA_FIELDS.get(entity_type, ()) if metadata.get(field) is not None}
    return {
        "type": entity_type,
        "id": canonical_id,
        "name": entity["name"],
        "url": entity.get("canonical_url") or None,
        "country_code": entity.get("country_code") or None,
        "fis_reference": {"type": FIS_LINK_TYPES[entity_type], "id": canonical_id} if entity_type in FIS_LINK_TYPES and entity.get("canonical_id") else None,
        "details": details,
    }


def build_pilot_export(submission, entities_by_id):
    required = ("id", "title", "sport", "status")
    missing = [field for field in required if not submission.get(field)]
    if missing:
        raise ValueError("Cannot create pilot JSON; missing: " + ", ".join(missing))

    stats = []
    for stat in sorted(submission.get("stats", []), key=lambda item: item.get("sort_order", 0)):
        formatted_text = (stat.get("edited_text") or stat.get("stat_text") or "").strip()
        text = rich_text_to_plain(formatted_text)
        if not text:
            raise ValueError("Cannot create pilot JSON with an empty statistic.")
        linked = []
        for entity_id in stat.get("entity_ids", []):
            entity = entities_by_id.get(entity_id)
            if not entity:
                continue
            exported_entity = _export_entity(entity)
            exported_entity["mention_text"] = (stat.get("entity_mentions") or {}).get(entity_id) or None
            linked.append(exported_entity)
        stats.append({"id": stat["id"], "type": stat.get("content_type", "stat"), "text": text, "formatted_text": formatted_text, "entities": linked})

    return {
        "schema_version": "pilot-1.1",
        "submission": {
            "id": submission["id"], "title": submission["title"], "sport": submission["sport"],
            "competition": submission.get("competition") or None,
            "event": {"name": submission.get("event_name") or None, "gender": submission.get("gender") or None, "location": submission.get("location") or None, "date": submission.get("event_date") or None},
            "status": submission["status"],
            "fis": {
                "external_id": submission.get("fis_external_id") or None,
                "discipline_code": submission.get("fis_discipline_code") or ("AL" if submission.get("sport") == "alpine_skiing" else None),
                "event_ids": [int(value) for value in submission.get("fis_event_ids", []) if str(value).isdigit()],
                "submission_note": submission.get("fis_submission_notes") or None,
            },
        },
        "stats": stats,
    }
