def build_pilot_export(submission, entities_by_id):
    required = ("id", "title", "sport", "status")
    missing = [field for field in required if not submission.get(field)]
    if missing:
        raise ValueError("Cannot create pilot JSON; missing: " + ", ".join(missing))

    stats = []
    for stat in sorted(submission.get("stats", []), key=lambda item: item.get("sort_order", 0)):
        text = (stat.get("edited_text") or stat.get("stat_text") or "").strip()
        if not text:
            raise ValueError("Cannot create pilot JSON with an empty statistic.")
        linked = []
        for entity_id in stat.get("entity_ids", []):
            entity = entities_by_id.get(entity_id)
            if not entity:
                continue
            linked.append({
                "type": entity["entity_type"],
                "id": entity.get("canonical_id") or entity["id"],
                "name": entity["name"],
                "url": entity.get("canonical_url") or None,
            })
        stats.append({"id": stat["id"], "text": text, "entities": linked})

    return {
        "schema_version": "pilot-1.0",
        "submission": {
            "id": submission["id"], "title": submission["title"], "sport": submission["sport"],
            "competition": submission.get("competition") or None,
            "event": {"name": submission.get("event_name") or None, "date": submission.get("event_date") or None},
            "status": submission["status"],
        },
        "stats": stats,
    }
