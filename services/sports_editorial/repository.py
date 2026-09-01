from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import os
import re
from flask import has_request_context

from .demo_data import fresh_demo_data
from .formatting import rich_text_to_plain, sanitise_rich_text
from .identifiers import build_fis_external_id
from .supabase_rest import SupabaseRestClient
from .validation import VALID_CONTENT_TYPES
from .edit_locks import lock_is_active, lock_timeout_seconds, public_lock


def _now():
    return datetime.now(timezone.utc).isoformat()


def _event_ids_from_form(form_data):
    values = re.split(r"[\s,]+", " ".join(form_data.getlist("fis_event_ids")))
    return list(dict.fromkeys(int(value) for value in values if value.isdigit() and int(value) > 0))[:10]


def _submitted_entity_links(form_data, block_id, allowed_ids, rich_text):
    """Keep inline links only while their exact confirmed wording still exists."""
    plain_text = rich_text_to_plain(rich_text)
    entity_ids = []
    mentions = {}
    ranges = {}
    for entity_id in form_data.getlist(f"entity_ids_{block_id}"):
        if entity_id not in allowed_ids or entity_id in entity_ids:
            continue
        mention = form_data.get(f"entity_mention_{block_id}_{entity_id}", "").strip()
        if mention:
            raw_start = form_data.get(f"entity_start_{block_id}_{entity_id}", "")
            raw_end = form_data.get(f"entity_end_{block_id}_{entity_id}", "")
            if raw_start.isdigit() and raw_end.isdigit():
                start, end = int(raw_start), int(raw_end)
                if start < end <= len(plain_text) and plain_text[start:end] == mention:
                    ranges[entity_id] = {"start": start, "end": end}
                else:
                    continue
            else:
                start = plain_text.find(mention)
                if start < 0:
                    continue
                ranges[entity_id] = {"start": start, "end": start + len(mention)}
        entity_ids.append(entity_id)
        if mention:
            mentions[entity_id] = mention
    return entity_ids, mentions, ranges


class DemoSportsEditorialRepository:
    """Process-local pilot repository. Replace this implementation, not the views, for Supabase."""

    def __init__(self):
        self._lock = RLock()
        self.reset()

    def reset(self):
        with self._lock:
            self._submissions, self._entities = fresh_demo_data()
            self._fis_publications = {}
            self._result_imports, self._results, self._audit_events = [], [], []

    def list_submissions(self, status="", sport="", order="newest"):
        from .auth import current_user
        user = current_user() or {}
        items = self._submissions
        if has_request_context() and user.get("role") == "researcher":
            items = [item for item in items if item.get("researcher_user_id") == user.get("id")]
        if status:
            items = [item for item in items if item["status"] == status]
        if sport:
            items = [item for item in items if item["sport"] == sport]
        items = sorted(items, key=lambda item: item.get("submitted_at") or item["created_at"], reverse=order != "oldest")
        return deepcopy(items)

    def get_submission(self, submission_id):
        from .auth import current_user
        item = next((item for item in self._submissions if item["id"] == submission_id), None)
        user = current_user() or {}
        if has_request_context() and item and user.get("role") == "researcher" and item.get("researcher_user_id") != user.get("id"):
            return None
        return deepcopy(item) if item else None

    def create_submission(self, data, status):
        now = _now()
        item = {
            "id": str(uuid4()), "title": data["title"].strip(), "sport": data.get("sport", "").strip() or "alpine_skiing",
            "competition": data.get("competition", "").strip(), "event_name": data.get("event_name", "").strip(),
            "gender": data.get("gender", "").strip().upper(), "location": data.get("location", "").strip(),
            "season_code": data.get("season_code"), "event_date": data.get("event_date", "").strip(), "fis_event_ids": data.get("fis_event_ids", []),
            "fis_external_id": build_fis_external_id(data), "author_name": data["author_name"].strip(),
            "author_email": data.get("author_email", "").strip(), "status": status, "editor_notes": "", "fis_submission_notes": "",
            "amp_id": "", "client_name": data.get("client_name", "").strip(),
            "publication_deadline": data.get("publication_deadline", ""), "researcher_deadline": data.get("researcher_deadline", ""),
            "researcher_user_id": data.get("researcher_user_id") or None, "researcher_name": data.get("researcher_name", ""),
            "sub_editor_user_id": data.get("sub_editor_user_id") or None, "sub_editor_name": data.get("sub_editor_name", ""),
            "working_notes": "", "unused_stats": "", "last_modified_by": data["author_name"].strip(),
            "created_at": now, "updated_at": now, "submitted_at": now if status == "submitted" else None, "approved_at": None,
            "stats": [{"id": str(uuid4()), "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "accepted_at": None, "accepted_by_user_id": None, "entity_ids": [], "entity_mentions": {}, "entity_ranges": {}, "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()],
        }
        with self._lock:
            # Demo allocation mirrors the production sequence without pretending
            # to provide cross-process production guarantees.
            allocated = [int(row["amp_id"]) for row in self._submissions if str(row.get("amp_id") or "").isdigit()]
            next_amp_id = max([560000, *allocated]) + 1
            if next_amp_id > 999999:
                raise RuntimeError("The six-digit AMP ID range is exhausted.")
            item["amp_id"] = str(next_amp_id)
            self._submissions.append(item)
        return deepcopy(item)

    def acquire_edit_lock(self, submission_id, user):
        with self._lock:
            item = next((row for row in self._submissions if row["id"] == submission_id), None)
            if not item:
                return None, None
            active = public_lock(item)
            if active and active["owner_id"] != user["id"]:
                return deepcopy(item), active
            same_owner = active and active["owner_id"] == user["id"]
            now = _now()
            if not same_owner:
                item["lock_token"] = str(uuid4())
                item["lock_acquired_at"] = now
                item["lock_version"] = int(item.get("lock_version") or 0) + 1
            item["lock_user_id"] = user["id"]
            item["lock_user_name"] = user.get("full_name") or user.get("email") or "Workspace user"
            item["lock_last_active_at"] = now
            if item.get("status") == "submitted":
                item["status"] = "in_review"
                item["updated_at"] = now
                item["last_modified_by"] = item["lock_user_name"]
            return deepcopy(item), public_lock(item)

    def heartbeat_edit_lock(self, submission_id, user_id, token):
        with self._lock:
            item = next((row for row in self._submissions if row["id"] == submission_id), None)
            if not item or not lock_is_active(item) or item.get("lock_user_id") != user_id or item.get("lock_token") != token:
                return None
            item["lock_last_active_at"] = _now()
            return public_lock(item)

    def force_takeover_edit_lock(self, submission_id, user):
        with self._lock:
            item = next((row for row in self._submissions if row["id"] == submission_id), None)
            if not item:
                return None, None
            now = _now()
            item["lock_user_id"] = user["id"]
            item["lock_user_name"] = user.get("full_name") or user.get("email") or "Workspace user"
            item["lock_token"] = str(uuid4())
            item["lock_acquired_at"] = now
            item["lock_last_active_at"] = now
            item["lock_version"] = int(item.get("lock_version") or 0) + 1
            if item.get("status") == "submitted":
                item["status"] = "in_review"
                item["updated_at"] = now
                item["last_modified_by"] = item["lock_user_name"]
            return deepcopy(item), public_lock(item)

    def verify_edit_lock(self, submission_id, user_id, token, version):
        item = next((row for row in self._submissions if row["id"] == submission_id), None)
        return bool(item and lock_is_active(item) and item.get("lock_user_id") == user_id
                    and item.get("lock_token") == token and int(item.get("lock_version") or 0) == int(version or -1))

    def release_edit_lock(self, submission_id, user_id=None, token=None, force=False):
        with self._lock:
            item = next((row for row in self._submissions if row["id"] == submission_id), None)
            if not item:
                return False
            if not force and (item.get("lock_user_id") != user_id or item.get("lock_token") != token):
                return False
            for field in ("lock_user_id", "lock_user_name", "lock_token", "lock_acquired_at", "lock_last_active_at"):
                item[field] = None
            item["lock_version"] = int(item.get("lock_version") or 0) + 1
            return True

    def get_edit_lock(self, submission_id):
        item = next((row for row in self._submissions if row["id"] == submission_id), None)
        return public_lock(item)

    def update_research(self, submission_id, form_data, submit=False):
        from .auth import current_user
        user = current_user() or {}
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            existing_by_id = {block["id"]: block for block in item.get("stats", [])}
            item["event_date"] = form_data.get("event_date", item.get("event_date", ""))
            item["working_notes"] = form_data.get("working_notes", "").strip()
            item["unused_stats"] = form_data.get("unused_stats", "").strip()
            blocks = []
            block_ids = form_data.getlist("content_id")
            for index, (kind, content) in enumerate(zip(form_data.getlist("content_type"), form_data.getlist("content_html"))):
                kind = "section" if kind == "heading" else kind
                if kind in ("stat", "section") and sanitise_rich_text(content).strip():
                    block_id = block_ids[index] if index < len(block_ids) and block_ids[index] else str(uuid4())
                    allowed_ids = {entity["id"] for entity in self._entities}
                    existing = existing_by_id.get(block_id, {})
                    clean = sanitise_rich_text(content)
                    entity_ids, mentions, entity_ranges = _submitted_entity_links(
                        form_data, block_id, allowed_ids, clean
                    )
                    changed = not existing or kind != existing.get("content_type") or clean != (existing.get("edited_text") or existing.get("stat_text") or "") or set(entity_ids) != set(existing.get("entity_ids", [])) or mentions != existing.get("entity_mentions", {}) or entity_ranges != existing.get("entity_ranges", {})
                    blocks.append({"id": block_id, "sort_order": index, "content_type": kind, "stat_text": clean if changed else existing.get("stat_text", clean), "edited_text": "" if changed else existing.get("edited_text", ""), "editor_comment": "", "accepted_at": None if changed else existing.get("accepted_at"), "accepted_by_user_id": None if changed else existing.get("accepted_by_user_id"), "entity_ids": entity_ids, "entity_mentions": mentions, "entity_ranges": entity_ranges, "tags": existing.get("tags", [])})
            item["stats"] = blocks
            item["status"] = "submitted" if submit else "draft"
            item["submitted_at"] = _now() if submit else item.get("submitted_at")
            item["updated_at"] = _now()
            item["last_modified_by"] = user.get("full_name") or user.get("email") or "Workspace user"
            return deepcopy(item)

    def update_review(self, submission_id, form_data, requested_status):
        from .auth import current_user
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            item["editor_notes"] = form_data.get("editor_notes", "").strip()
            item["fis_submission_notes"] = form_data.get("fis_submission_notes", "").strip()
            item["fis_event_ids"] = _event_ids_from_form(form_data)
            for field in ("title", "amp_id", "client_name", "competition", "event_name", "gender", "location", "season_code", "event_date", "publication_deadline", "researcher_deadline", "researcher_user_id", "researcher_name", "sub_editor_user_id", "sub_editor_name", "working_notes", "unused_stats"):
                if field in form_data:
                    item[field] = form_data.get(field, "").strip() or None
            if item.get("season_code"):
                item["season_code"] = int(item["season_code"])
            demo_names = {"demo-user": "Jamie Laurent", "demo-researcher-2": "Andrew Hendry", "demo-sub-editor": "Nick L.", "demo-supervisor": "Supervisor Demo"}
            item["researcher_name"] = demo_names.get(item.get("researcher_user_id"), "Unassigned")
            item["sub_editor_name"] = demo_names.get(item.get("sub_editor_user_id"), "Unassigned")
            ordered_ids = form_data.getlist("content_id")
            if ordered_ids:
                existing_by_id = {block["id"]: block for block in item["stats"]}
                kinds = form_data.getlist("content_type")
                rebuilt = []
                for index, block_id in enumerate(ordered_ids):
                    kind = kinds[index] if index < len(kinds) and kinds[index] in ("stat", "section") else "stat"
                    block = existing_by_id.get(block_id) or {"id": block_id or str(uuid4()), "stat_text": sanitise_rich_text(form_data.get(f"edited_text_{block_id}", "")), "edited_text": "", "editor_comment": "", "accepted_at": None, "accepted_by_user_id": None, "entity_ids": [], "entity_mentions": {}, "entity_ranges": {}, "tags": []}
                    block["content_type"], block["sort_order"] = kind, index
                    rebuilt.append(block)
                item["stats"] = rebuilt
            for stat in item["stats"]:
                stat_id = stat["id"]
                stat["edited_text"] = sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", stat.get("edited_text") or stat.get("stat_text", "")))
                stat["editor_comment"] = form_data.get(f"editor_comment_{stat_id}", "").strip()
                accepted = stat.get("content_type") in ("stat", "section", "heading") and form_data.get(f"accepted_{stat_id}") == "1"
                stat["accepted_at"] = _now() if accepted else None
                stat["accepted_by_user_id"] = (current_user() or {}).get("id") if accepted else None
                stat["tags"] = [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()]
                allowed_ids = {entity["id"] for entity in self._entities}
                stat["entity_ids"], stat["entity_mentions"], stat["entity_ranges"] = _submitted_entity_links(
                    form_data, stat_id, allowed_ids, stat["edited_text"]
                )
            item["status"] = requested_status
            item["updated_at"] = _now()
            user = current_user() or {}
            item["last_modified_by"] = user.get("full_name") or user.get("email") or "Workspace user"
            if requested_status == "approved" and not item["approved_at"]:
                item["approved_at"] = item["updated_at"]
            return deepcopy(item)

    def get_fis_publication(self, submission_id):
        return deepcopy(self._fis_publications.get(submission_id))

    def save_fis_publication(self, submission_id, publication):
        with self._lock:
            self._fis_publications[submission_id] = deepcopy(publication)
        return deepcopy(publication)

    def set_submission_status(self, submission_id, status):
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            item["status"] = status
            item["updated_at"] = _now()
        return deepcopy(item)

    def record_audit_event(self, submission_id, actor, action, details=None):
        event = {
            "id": str(uuid4()), "submission_id": submission_id,
            "actor_user_id": actor.get("id"), "actor_name": actor.get("full_name") or actor.get("email"),
            "action": action, "details": deepcopy(details or {}), "created_at": _now(),
        }
        with self._lock:
            self._audit_events.append(event)
        return deepcopy(event)

    def list_audit_events(self, submission_id):
        return deepcopy([event for event in self._audit_events if event["submission_id"] == submission_id])

    def bulk_assign(self, submission_ids, assignment_field, user_id, user_name, actor_id, actor_name):
        if assignment_field not in ("researcher_user_id", "sub_editor_user_id"):
            raise ValueError("Unsupported assignment field.")
        wanted = set(submission_ids)
        with self._lock:
            selected = [item for item in self._submissions if item["id"] in wanted]
            if len(selected) != len(wanted):
                raise ValueError("One or more selected stat sheets no longer exist.")
            name_field = "researcher_name" if assignment_field == "researcher_user_id" else "sub_editor_name"
            now = _now()
            for item in selected:
                item[assignment_field] = user_id
                item[name_field] = user_name or "Unassigned"
                item["updated_at"] = now
                item["last_modified_by"] = actor_name
        return len(selected)

    def list_entities(self, entity_type="", limit=None):
        items = [item for item in self._entities if not entity_type or item["entity_type"] == entity_type]
        items = sorted(items, key=lambda item: (item["entity_type"], item["name"]))
        return deepcopy(items[:limit] if limit else items)

    def get_entities_by_ids(self, entity_ids):
        wanted = set(entity_ids)
        return deepcopy([item for item in self._entities if item["id"] in wanted])

    def search_entities(self, query, entity_type="", limit=10, offset=0):
        needle = query.casefold().strip()

        def searchable_values(entity):
            return tuple(
                str(entity.get(field) or "").casefold()
                for field in ("name", "country_code", "canonical_id")
                if entity.get(field)
            )

        matches = [
            entity for entity in self._entities
            if (not entity_type or entity["entity_type"] == entity_type)
            and any(needle in value for value in searchable_values(entity))
        ]
        ranked = sorted(matches, key=lambda item: (
            not any(value == needle for value in searchable_values(item)),
            not any(value.startswith(needle) for value in searchable_values(item)),
            item["name"].casefold(),
        ))
        return deepcopy(ranked[offset:offset + limit])

    def add_entity(self, data):
        entity = {"id": str(uuid4()), "entity_type": data["entity_type"], "name": data["name"].strip(), "canonical_id": data.get("canonical_id", "").strip(), "canonical_url": data.get("canonical_url", "").strip(), "country_code": data.get("country_code", "").strip().upper()}
        with self._lock:
            self._entities.append(entity)
        return deepcopy(entity)

    def upsert_calendar_events(self, events):
        with self._lock:
            for incoming in events:
                existing = next((item for item in self._entities if item["entity_type"] == "event" and item.get("canonical_id") == incoming["canonical_id"]), None)
                if existing:
                    existing.update(deepcopy(incoming))
                else:
                    self._entities.append({"id": str(uuid4()), **deepcopy(incoming)})
        return len(events)

    def upsert_athletes(self, athletes):
        with self._lock:
            for incoming in athletes:
                existing = next((item for item in self._entities if item["entity_type"] == "athlete" and item.get("canonical_id") == incoming["canonical_id"]), None)
                if existing:
                    existing.update(deepcopy(incoming))
                else:
                    self._entities.append({"id": str(uuid4()), **deepcopy(incoming)})
        return len(athletes)

    def upsert_entities(self, entities):
        with self._lock:
            for incoming in entities:
                existing = next((item for item in self._entities if item["entity_type"] == incoming["entity_type"] and item.get("canonical_id") == incoming["canonical_id"]), None)
                if existing:
                    existing.update(deepcopy(incoming))
                else:
                    self._entities.append({"id": str(uuid4()), **deepcopy(incoming)})
        return len(entities)

    def list_result_competitions(self):
        return deepcopy(sorted(self._result_imports, key=lambda item: item.get("race_date") or "", reverse=True))

    def list_results(self, race_ids=None):
        wanted = {str(value) for value in (race_ids or [])}
        rows = self._results if not wanted else [row for row in self._results if str(row.get("race_id")) in wanted]
        imports = {str(item["race_id"]): item for item in self._result_imports}
        hydrated = []
        for row in rows:
            item = deepcopy(row)
            imported = imports.get(str(row["race_id"]), {})
            item["season_code"] = imported.get("season_code")
            item["competition"] = imported.get("category_code") or item.get("competition")
            hydrated.append(item)
        return hydrated

    def save_result_import(self, race, rows, partial=False):
        if not rows:
            return 0
        first = rows[0]
        race_id = str(first["race_id"])
        record = _result_import_record(race, rows, partial)
        with self._lock:
            self._result_imports = [item for item in self._result_imports if str(item["race_id"]) != race_id]
            self._result_imports.append(record)
            self._results = [item for item in self._results if str(item["race_id"]) != race_id] + deepcopy(rows)
            self.upsert_athletes(_result_athlete_entities(rows))
        return len(rows)


class SupabaseSportsEditorialRepository:
    """Workspace-scoped persistence using the isolated sports_editorial_* tables."""

    def __init__(self, client=None, workspace_id=None):
        self.client = client or SupabaseRestClient()
        self.workspace_id = workspace_id

    def reset(self):
        # Tests use the demo repository. Never delete shared Supabase data here.
        return None

    def _workspace(self):
        if self.workspace_id:
            return self.workspace_id
        from .auth import current_user
        user = current_user()
        return user["workspace_id"] if user else ""

    def _hydrate(self, rows):
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        stats = self.client.request("sports_editorial_stats", query={"select": "*", "submission_id": f"in.({','.join(ids)})", "order": "sort_order.asc"})
        stat_ids = [row["id"] for row in stats]
        links = self.client.request("sports_editorial_stat_entities", query={"select": "stat_id,entity_id,relationship_type,mention_text,mention_start,mention_end", "stat_id": f"in.({','.join(stat_ids)})"}) if stat_ids else []
        entity_ids = {}
        entity_mentions = {}
        entity_ranges = {}
        for link in links:
            entity_ids.setdefault(link["stat_id"], []).append(link["entity_id"])
            if link.get("mention_text"):
                entity_mentions.setdefault(link["stat_id"], {})[link["entity_id"]] = link["mention_text"]
            if link.get("mention_start") is not None and link.get("mention_end") is not None:
                entity_ranges.setdefault(link["stat_id"], {})[link["entity_id"]] = {
                    "start": link["mention_start"], "end": link["mention_end"]
                }
        by_submission = {}
        for stat in stats:
            stat["entity_ids"] = entity_ids.get(stat["id"], [])
            stat["entity_mentions"] = entity_mentions.get(stat["id"], {})
            stat["entity_ranges"] = entity_ranges.get(stat["id"], {})
            by_submission.setdefault(stat["submission_id"], []).append(stat)
        for row in rows:
            row["stats"] = by_submission.get(row["id"], [])
        user_ids = list(dict.fromkeys(value for row in rows for value in (row.get("researcher_user_id"), row.get("sub_editor_user_id")) if value))
        if user_ids:
            users = self.client.request("app_users", query={"select": "id,full_name,email", "id": f"in.({','.join(user_ids)})"})
            users_by_id = {item["id"]: item for item in users}
            for row in rows:
                researcher = users_by_id.get(row.get("researcher_user_id"), {})
                sub_editor = users_by_id.get(row.get("sub_editor_user_id"), {})
                row["researcher_name"] = researcher.get("full_name") or researcher.get("email") or "Unassigned"
                row["sub_editor_name"] = sub_editor.get("full_name") or sub_editor.get("email") or "Unassigned"
                row["last_modified_by"] = row.get("last_modified_by_name") or "—"
        return rows

    def list_submissions(self, status="", sport="", order="newest"):
        from .auth import current_user
        user = current_user() or {}
        query = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "order": f"submitted_at.{'desc' if order != 'oldest' else 'asc'}.nullslast"}
        if user.get("role") == "researcher":
            query["researcher_user_id"] = f"eq.{user.get('id')}"
        if status:
            query["status"] = f"eq.{status}"
        if sport:
            query["sport"] = f"eq.{sport}"
        return self._hydrate(self.client.request("sports_editorial_submissions", query=query))

    def get_submission(self, submission_id):
        from .auth import current_user
        user = current_user() or {}
        rows = self.client.request("sports_editorial_submissions", query={"select": "*", "id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}", "limit": "1"})
        if rows and user.get("role") == "researcher" and rows[0].get("researcher_user_id") != user.get("id"):
            return None
        hydrated = self._hydrate(rows)
        return hydrated[0] if hydrated else None

    def create_submission(self, data, status):
        from .auth import current_user
        user = current_user() or {}
        now = _now()
        submission = {
            "workspace_id": self._workspace(), "author_user_id": user.get("id"), "title": data["title"].strip(),
            "sport": "alpine_skiing", "competition": data.get("competition", "").strip(), "event_name": data.get("event_name", "").strip(),
            "gender": data.get("gender", "").strip().upper() or None, "location": data.get("location", "").strip(),
            "season_code": data.get("season_code"), "event_date": data.get("event_date") or None, "fis_event_ids": data.get("fis_event_ids", []),
            "fis_external_id": build_fis_external_id(data), "author_name": data["author_name"].strip(), "author_email": data.get("author_email", "").strip(),
            "status": status, "editor_notes": "", "fis_submission_notes": "", "submitted_at": now if status == "submitted" else None,
            # AMP ID is assigned atomically by the database default.
            "client_name": data.get("client_name", ""),
            "publication_deadline": data.get("publication_deadline") or None, "researcher_deadline": data.get("researcher_deadline") or None,
            "researcher_user_id": data.get("researcher_user_id") or None, "sub_editor_user_id": data.get("sub_editor_user_id") or None,
            "working_notes": "", "unused_stats": "", "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email"),
        }
        created = self.client.request("sports_editorial_submissions", "POST", payload=submission, prefer="return=representation")[0]
        blocks = [{"submission_id": created["id"], "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "accepted_at": None, "accepted_by_user_id": None, "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()]
        if blocks:
            self.client.request("sports_editorial_stats", "POST", payload=blocks, prefer="return=minimal")
        return self.get_submission(created["id"])

    def acquire_edit_lock(self, submission_id, user):
        rows = self.client.request("rpc/sports_editorial_acquire_edit_lock", "POST", payload={
            "p_workspace_id": self._workspace(), "p_submission_id": submission_id,
            "p_user_id": user["id"], "p_user_name": user.get("full_name") or user.get("email") or "Workspace user",
            "p_timeout_seconds": lock_timeout_seconds(),
        })
        item = self._hydrate(rows)[0] if rows else self.get_submission(submission_id)
        return item, public_lock(item)

    def heartbeat_edit_lock(self, submission_id, user_id, token):
        rows = self.client.request("rpc/sports_editorial_heartbeat_edit_lock", "POST", payload={
            "p_workspace_id": self._workspace(), "p_submission_id": submission_id,
            "p_user_id": user_id, "p_lock_token": token, "p_timeout_seconds": lock_timeout_seconds(),
        })
        return public_lock(rows[0]) if rows else None

    def force_takeover_edit_lock(self, submission_id, user):
        rows = self.client.request("rpc/sports_editorial_force_takeover_edit_lock", "POST", payload={
            "p_workspace_id": self._workspace(), "p_submission_id": submission_id,
            "p_user_id": user["id"], "p_user_name": user.get("full_name") or user.get("email") or "Workspace user",
        })
        item = self._hydrate(rows)[0] if rows else self.get_submission(submission_id)
        return item, public_lock(item)

    def verify_edit_lock(self, submission_id, user_id, token, version):
        item = self.get_submission(submission_id)
        return bool(item and lock_is_active(item) and item.get("lock_user_id") == user_id
                    and str(item.get("lock_token")) == str(token)
                    and int(item.get("lock_version") or 0) == int(version or -1))

    def release_edit_lock(self, submission_id, user_id=None, token=None, force=False):
        if force:
            rows = self.client.request("rpc/sports_editorial_force_unlock", "POST", payload={
                "p_workspace_id": self._workspace(), "p_submission_id": submission_id,
            })
            return bool(rows)
        query = {"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}",
                 "lock_user_id": f"eq.{user_id}", "lock_token": f"eq.{token}"}
        payload = {"lock_user_id": None, "lock_user_name": None, "lock_token": None,
                   "lock_acquired_at": None, "lock_last_active_at": None}
        rows = self.client.request("sports_editorial_submissions", "PATCH", query=query, payload=payload, prefer="return=representation")
        return bool(rows)

    def get_edit_lock(self, submission_id):
        return public_lock(self.get_submission(submission_id))

    def update_research(self, submission_id, form_data, submit=False):
        from .auth import current_user
        user = current_user() or {}
        now = _now()
        changes = {"event_date": form_data.get("event_date") or None, "working_notes": form_data.get("working_notes", "").strip(), "unused_stats": form_data.get("unused_stats", "").strip(), "status": "submitted" if submit else "draft", "updated_at": now, "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email")}
        if submit:
            changes["submitted_at"] = now
        query = {"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}"}
        if user.get("role") == "researcher":
            query["researcher_user_id"] = f"eq.{user.get('id')}"
        self.client.request("sports_editorial_submissions", "PATCH", query=query, payload=changes, prefer="return=minimal")
        existing = self.get_submission(submission_id)
        existing_by_id = {stat["id"]: stat for stat in existing.get("stats", [])}
        for stat in existing.get("stats", []):
            self.client.request("sports_editorial_stats", "DELETE", query={"id": f"eq.{stat['id']}"})
        blocks = []
        submitted_links = {}
        block_ids = form_data.getlist("content_id")
        for index, (kind, content) in enumerate(zip(form_data.getlist("content_type"), form_data.getlist("content_html"))):
            kind = "section" if kind == "heading" else kind
            clean = sanitise_rich_text(content)
            if kind in ("stat", "section") and clean.strip():
                block_id = block_ids[index] if index < len(block_ids) and block_ids[index] else str(uuid4())
                existing_block = existing_by_id.get(block_id, {})
                requested_ids, mentions, ranges = _submitted_entity_links(
                    form_data,
                    block_id,
                    {entity["id"] for entity in self.get_entities_by_ids(form_data.getlist(f"entity_ids_{block_id}"))},
                    clean,
                )
                submitted_links[block_id] = (requested_ids, mentions, ranges)
                changed = not existing_block or kind != existing_block.get("content_type") or clean != (existing_block.get("edited_text") or existing_block.get("stat_text") or "") or set(requested_ids) != set(existing_block.get("entity_ids", [])) or mentions != existing_block.get("entity_mentions", {}) or ranges != existing_block.get("entity_ranges", {})
                blocks.append({"id": block_id, "submission_id": submission_id, "sort_order": index, "content_type": kind, "stat_text": clean if changed else existing_block.get("stat_text", clean), "edited_text": "" if changed else existing_block.get("edited_text", ""), "editor_comment": "", "accepted_at": None if changed else existing_block.get("accepted_at"), "accepted_by_user_id": None if changed else existing_block.get("accepted_by_user_id"), "tags": existing_block.get("tags", [])})
        if blocks:
            self.client.request("sports_editorial_stats", "POST", payload=blocks, prefer="return=minimal")
            requested_ids = [
                value for block in blocks
                for value in submitted_links.get(block["id"], ([], {}, {}))[0]
            ]
            allowed_ids = {entity["id"] for entity in self.get_entities_by_ids(requested_ids)}
            links = []
            for block in blocks:
                entity_ids, mentions, ranges = submitted_links.get(block["id"], ([], {}, {}))
                for entity_id in entity_ids:
                    if entity_id in allowed_ids:
                        mention = mentions.get(entity_id, "")
                        entity_range = ranges.get(entity_id, {})
                        links.append({"stat_id": block["id"], "entity_id": entity_id, "relationship_type": "inline" if mention else "about", "mention_text": mention or None, "mention_start": entity_range.get("start"), "mention_end": entity_range.get("end")})
            if links:
                self.client.request("sports_editorial_stat_entities", "POST", payload=links, prefer="return=minimal")
        return self.get_submission(submission_id)

    def update_review(self, submission_id, form_data, requested_status):
        from .auth import current_user
        user = current_user() or {}
        item = self.get_submission(submission_id)
        ordered_ids = form_data.getlist("content_id")
        if ordered_ids:
            kinds = form_data.getlist("content_type")
            existing_by_id = {block["id"]: block for block in item["stats"]}
            removed_ids = [block_id for block_id in existing_by_id if block_id not in ordered_ids]
            for block_id in removed_ids:
                self.client.request("sports_editorial_stats", "DELETE", query={"id": f"eq.{block_id}", "submission_id": f"eq.{submission_id}"})
            new_blocks = []
            ordered_blocks = []
            for index, block_id in enumerate(ordered_ids):
                kind = kinds[index] if index < len(kinds) and kinds[index] in ("stat", "section") else "stat"
                block = existing_by_id.get(block_id)
                if not block:
                    wording = sanitise_rich_text(form_data.get(f"edited_text_{block_id}", ""))
                    block = {"id": block_id, "submission_id": submission_id, "sort_order": index, "content_type": kind, "stat_text": wording, "edited_text": wording, "editor_comment": "", "accepted_at": None, "accepted_by_user_id": None, "tags": [], "entity_ids": [], "entity_mentions": {}, "entity_ranges": {}}
                    new_blocks.append({key: block[key] for key in ("id", "submission_id", "sort_order", "content_type", "stat_text", "edited_text", "editor_comment", "accepted_at", "accepted_by_user_id", "tags")})
                block["content_type"], block["sort_order"] = kind, index
                ordered_blocks.append(block)
            if new_blocks:
                self.client.request("sports_editorial_stats", "POST", payload=new_blocks, prefer="return=minimal")
            item["stats"] = ordered_blocks
        requested_entity_ids = [
            value for stat in item["stats"]
            for value in form_data.getlist(f"entity_ids_{stat['id']}")
        ]
        allowed_ids = {entity["id"] for entity in self.get_entities_by_ids(requested_entity_ids)}
        for stat in item["stats"]:
            stat_id = stat["id"]
            accepted = stat.get("content_type") in ("stat", "section", "heading") and form_data.get(f"accepted_{stat_id}") == "1"
            edited_text = sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", stat.get("edited_text") or stat.get("stat_text", "")))
            self.client.request("sports_editorial_stats", "PATCH", query={"id": f"eq.{stat_id}"}, payload={"sort_order": stat.get("sort_order", 0), "content_type": stat.get("content_type", "stat"), "edited_text": edited_text, "editor_comment": form_data.get(f"editor_comment_{stat_id}", "").strip(), "tags": [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()], "accepted_at": _now() if accepted else None, "accepted_by_user_id": user.get("id") if accepted else None, "updated_at": _now()}, prefer="return=minimal")
            selected, mentions, ranges = _submitted_entity_links(
                form_data, stat_id, allowed_ids, edited_text
            )
            self.client.request("sports_editorial_stat_entities", "DELETE", query={"stat_id": f"eq.{stat_id}"})
            if selected:
                self.client.request("sports_editorial_stat_entities", "POST", payload=[{
                    "stat_id": stat_id, "entity_id": value,
                    "relationship_type": "inline" if mentions.get(value) else "about",
                    "mention_text": mentions.get(value) or None,
                    "mention_start": (ranges.get(value) or {}).get("start"),
                    "mention_end": (ranges.get(value) or {}).get("end"),
                } for value in selected], prefer="return=minimal")
        event_ids = _event_ids_from_form(form_data)
        changes = {"status": requested_status, "editor_notes": form_data.get("editor_notes", "").strip(), "fis_submission_notes": form_data.get("fis_submission_notes", "").strip(), "fis_event_ids": event_ids, "updated_at": _now(), "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email")}
        for field in ("title", "amp_id", "client_name", "competition", "event_name", "gender", "location", "season_code", "event_date", "publication_deadline", "researcher_deadline", "researcher_user_id", "sub_editor_user_id", "working_notes", "unused_stats"):
            if field in form_data:
                changes[field] = form_data.get(field) or None
        if changes.get("season_code"):
            changes["season_code"] = int(changes["season_code"])
        if requested_status == "approved" and not item.get("approved_at"):
            changes["approved_at"] = changes["updated_at"]
        self.client.request("sports_editorial_submissions", "PATCH", query={"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}"}, payload=changes, prefer="return=minimal")
        return self.get_submission(submission_id)

    def get_fis_publication(self, submission_id):
        item = self.get_submission(submission_id)
        return (item or {}).get("fis_publication")

    def save_fis_publication(self, submission_id, publication):
        self.client.request("sports_editorial_submissions", "PATCH", query={"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}"}, payload={"fis_publication": publication, "updated_at": _now()}, prefer="return=minimal")
        return publication

    def set_submission_status(self, submission_id, status):
        self.client.request("sports_editorial_submissions", "PATCH", query={"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}"}, payload={"status": status, "updated_at": _now()}, prefer="return=minimal")
        return self.get_submission(submission_id)

    def record_audit_event(self, submission_id, actor, action, details=None):
        payload = {
            "workspace_id": self._workspace(), "submission_id": submission_id,
            "actor_user_id": actor.get("id"), "actor_name": actor.get("full_name") or actor.get("email"),
            "action": action, "details": details or {},
        }
        rows = self.client.request("sports_editorial_audit_events", "POST", payload=payload, prefer="return=representation")
        return rows[0] if rows else None

    def list_audit_events(self, submission_id):
        return self.client.request("sports_editorial_audit_events", query={
            "select": "*", "workspace_id": f"eq.{self._workspace()}",
            "submission_id": f"eq.{submission_id}", "order": "created_at.desc",
        })

    def bulk_assign(self, submission_ids, assignment_field, user_id, user_name, actor_id, actor_name):
        if assignment_field not in ("researcher_user_id", "sub_editor_user_id"):
            raise ValueError("Unsupported assignment field.")
        ids = list(dict.fromkeys(submission_ids))
        id_filter = f"in.({','.join(ids)})"
        query = {"select": "id", "id": id_filter, "workspace_id": f"eq.{self._workspace()}"}
        existing = self.client.request("sports_editorial_submissions", query=query)
        if len(existing) != len(ids):
            raise ValueError("One or more selected stat sheets no longer exist.")
        changes = {
            assignment_field: user_id,
            "updated_at": _now(),
            "last_modified_by_user_id": actor_id,
            "last_modified_by_name": actor_name,
        }
        self.client.request(
            "sports_editorial_submissions", "PATCH",
            query={"id": id_filter, "workspace_id": f"eq.{self._workspace()}"},
            payload=changes, prefer="return=minimal",
        )
        return len(ids)

    def list_entities(self, entity_type="", limit=None):
        query = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "order": "entity_type.asc,name.asc"}
        if entity_type:
            query["entity_type"] = f"eq.{entity_type}"
        if limit:
            query["limit"] = str(limit)
        return self.client.request("sports_editorial_entities", query=query)

    def get_entities_by_ids(self, entity_ids):
        ids = list(dict.fromkeys(entity_ids))
        if not ids:
            return []
        return self.client.request("sports_editorial_entities", query={"select": "*", "workspace_id": f"eq.{self._workspace()}", "id": f"in.({','.join(ids)})"})

    def search_entities(self, query, entity_type="", limit=10, offset=0):
        needle = query.casefold().strip()
        wanted = offset + limit
        matches = []
        seen = set()

        # Query exact, prefix, then substring matches so relevance is stable
        # without changing the entity table or depending on DB collation.
        for pattern in (query, f"{query}*", f"*{query}*"):
            params = {
                "select": "*",
                "workspace_id": f"eq.{self._workspace()}",
                "or": f"(name.ilike.{pattern},country_code.ilike.{pattern},canonical_id.ilike.{pattern})",
                "limit": str(wanted),
                "order": "name.asc",
            }
            if entity_type:
                params["entity_type"] = f"eq.{entity_type}"
            for item in self.client.request("sports_editorial_entities", query=params):
                if item["id"] not in seen:
                    matches.append(item)
                    seen.add(item["id"])
            if len(matches) >= wanted:
                break

        def searchable_values(item):
            return tuple(
                str(item.get(field) or "").casefold()
                for field in ("name", "country_code", "canonical_id")
                if item.get(field)
            )

        matches.sort(key=lambda item: (
            not any(value == needle for value in searchable_values(item)),
            not any(value.startswith(needle) for value in searchable_values(item)),
            item["name"].casefold(),
        ))
        return matches[offset:wanted]

    def add_entity(self, data):
        payload = {"workspace_id": self._workspace(), "entity_type": data["entity_type"], "name": data["name"].strip(), "canonical_id": data.get("canonical_id", "").strip() or None, "canonical_url": data.get("canonical_url", "").strip() or None, "country_code": data.get("country_code", "").strip().upper() or None}
        return self.client.request("sports_editorial_entities", "POST", payload=payload, prefer="return=representation")[0]

    def upsert_calendar_events(self, events):
        payload = [{**event, "workspace_id": self._workspace()} for event in events]
        if payload:
            self.client.request(
                "sports_editorial_entities", "POST",
                query={"on_conflict": "workspace_id,entity_type,canonical_id"},
                payload=payload,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(payload)

    def upsert_athletes(self, athletes):
        for start in range(0, len(athletes), 500):
            payload = [{**athlete, "workspace_id": self._workspace()} for athlete in athletes[start:start + 500]]
            self.client.request(
                "sports_editorial_entities", "POST",
                query={"on_conflict": "workspace_id,entity_type,canonical_id"},
                payload=payload,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(athletes)

    def upsert_entities(self, entities):
        for start in range(0, len(entities), 500):
            payload = [{**entity, "workspace_id": self._workspace()} for entity in entities[start:start + 500]]
            self.client.request(
                "sports_editorial_entities", "POST",
                query={"on_conflict": "workspace_id,entity_type,canonical_id"},
                payload=payload,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(entities)

    def list_result_competitions(self):
        rows = []
        page_size = 500
        offset = 0

        while True:
            page = self.client.request(
                "sports_editorial_result_imports",
                query={
                    "select": "*",
                    "workspace_id": f"eq.{self._workspace()}",
                    "order": "race_date.desc.nullslast,race_id.desc",
                    "limit": str(page_size),
                    "offset": str(offset),
                },
            )

            rows.extend(page)

            if len(page) < page_size:
                break

            offset += page_size

        return rows

    def list_results(self, race_ids=None):
        query = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "order": "race_id.asc,place.asc.nullslast"}
        ids = list(dict.fromkeys(str(value) for value in (race_ids or []) if str(value).isdigit()))
        if ids:
            query["race_id"] = f"in.({','.join(ids)})"
        rows = []
        page_size = 1000
        for offset in range(0, 250000, page_size):
            page = self.client.request("sports_editorial_results", query={**query, "limit": str(page_size), "offset": str(offset)})
            rows.extend(page)
            if len(page) < page_size:
                break
        imports = {str(item["race_id"]): item for item in self.list_result_competitions()}
        return [_hydrate_result_row(row, imports.get(str(row["race_id"]), {})) for row in rows]

    def save_result_import(self, race, rows, partial=False):
        if not rows:
            return 0
        record = {**_result_import_record(race, rows, partial), "workspace_id": self._workspace()}
        self.client.request("sports_editorial_result_imports", "POST",
                            query={"on_conflict": "workspace_id,race_id"}, payload=record,
                            prefer="resolution=merge-duplicates,return=minimal")
        payload = [_result_storage_row(self._workspace(), row) for row in rows]
        for start in range(0, len(payload), 250):
            self.client.request("sports_editorial_results", "POST",
                                query={"on_conflict": "workspace_id,race_id,fis_code"}, payload=payload[start:start + 250],
                                prefer="resolution=merge-duplicates,return=minimal")
        # Official result pages include retired competitors who are absent from
        # the current-season points list. Promote those local records into the
        # same entity catalogue so autocomplete can find historic athletes too.
        self.upsert_athletes(_result_athlete_entities(rows))
        current_codes = ",".join(str(row["fis_code"]) for row in payload)
        if current_codes:
            self.client.request("sports_editorial_results", "DELETE", query={
                "workspace_id": f"eq.{self._workspace()}", "race_id": f"eq.{record['race_id']}", "fis_code": f"not.in.({current_codes})",
            }, prefer="return=minimal")
        return len(payload)


def _result_athlete_entities(rows):
    athletes = {}
    for row in rows:
        fis_code = str(row.get("fis_code") or "").strip()
        competitor_id = str(row.get("competitor_id") or "").strip()
        name = str(row.get("athlete") or row.get("athlete_name") or "").strip()
        nation = str(row.get("nation") or row.get("nation_code") or "").strip().upper()
        if not re.fullmatch(r"-?\d+", fis_code) or not name:
            continue
        athletes[fis_code] = {
            "entity_type": "athlete",
            "name": name,
            "canonical_id": fis_code,
            "canonical_url": (
                "https://www.fis-ski.com/DB/general/athlete-biography.html"
                f"?competitorid={competitor_id}&sectorcode=AL"
            ) if competitor_id.isdigit() else "",
            "country_code": nation if re.fullmatch(r"[A-Z]{3}", nation) else None,
            "metadata": {
                "competitor_id": competitor_id or None,
                "source_name": "fis_official_results",
            },
        }
    return list(athletes.values())


def _result_import_record(race, rows, partial=False):
    first = rows[0]
    now = _now()
    metadata = race.get("metadata") or {}
    return {
        "race_id": int(first["race_id"]), "event_id": int(metadata["event_id"]) if str(metadata.get("event_id") or "").isdigit() else None,
        "season_code": int(metadata["season_code"]) if str(metadata.get("season_code") or "").isdigit() else None,
        "discipline_code": "AL", "event_code": first.get("discipline") or metadata.get("event_code"),
        "category_code": first.get("competition") or metadata.get("category_code"), "gender": first.get("gender") or metadata.get("gender") or None,
        "venue": first.get("venue"), "nation_code": race.get("country_code") or None, "race_date": first.get("date") or None,
        "source_url": first.get("source_url") or race.get("canonical_url") or "", "source_name": "fis_official_results",
        "import_status": "partial" if partial else "complete", "row_count": len(rows), "last_error": None,
        "imported_at": first.get("imported_at") or now, "refreshed_at": now,
    }


def _result_storage_row(workspace_id, row):
    def integer(value):
        return int(value) if str(value or "").isdigit() else None
    return {
        "workspace_id": workspace_id, "race_id": int(row["race_id"]), "fis_code": int(row["fis_code"]),
        "competitor_id": integer(row.get("competitor_id")), "athlete_name": row["athlete"], "nation_code": row["nation"],
        "bib": integer(row.get("bib")), "birth_year": integer(row.get("birth_year")), "place": row.get("place"),
        "result_status": row.get("status") or "finished",
        "total_time": row.get("total_time") or (row.get("time") if not str(row.get("time") or "").startswith("+") else None),
        "diff_time": row.get("diff_time") or (row.get("time") if str(row.get("time") or "").startswith("+") else None),
        "fis_points": row.get("fis_points"), "cup_points": row.get("cup_points"),
        "source_url": row.get("source_url") or "", "imported_at": row.get("imported_at") or _now(),
    }


def _hydrate_result_row(row, imported):
    return {
        "race_id": str(row["race_id"]), "date": imported.get("race_date") or "", "venue": imported.get("venue") or "FIS event",
        "discipline": imported.get("event_code") or "AL", "gender": imported.get("gender") or "",
        "host_nation": imported.get("nation_code") or "",
        "season_code": imported.get("season_code"),
        "competition": imported.get("category_code") or "FIS", "place": row.get("place"), "status": row.get("result_status"),
        "athlete": row.get("athlete_name"), "fis_code": str(row.get("fis_code") or ""),
        "competitor_id": str(row.get("competitor_id") or ""), "nation": row.get("nation_code"),
        "bib": str(row.get("bib") or ""), "birth_year": str(row.get("birth_year") or ""),
        "time": row.get("total_time") or row.get("diff_time") or "", "total_time": row.get("total_time") or "",
        "diff_time": row.get("diff_time") or "", "fis_points": row.get("fis_points"), "cup_points": row.get("cup_points"),
        "source_url": row.get("source_url") or imported.get("source_url") or "", "source": "fis_official_results",
        "imported_at": row.get("imported_at") or imported.get("imported_at"),
    }


def _build_repository():
    if os.getenv("SPORTS_EDITORIAL_REPOSITORY", "demo").strip().lower() == "supabase":
        client = SupabaseRestClient()
        if client.configured:
            return SupabaseSportsEditorialRepository(client)
    return DemoSportsEditorialRepository()


repository = _build_repository()
