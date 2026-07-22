from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import os
import re
from flask import has_request_context

from .demo_data import fresh_demo_data
from .formatting import sanitise_rich_text
from .identifiers import build_fis_external_id
from .supabase_rest import SupabaseRestClient
from .validation import VALID_CONTENT_TYPES


def _now():
    return datetime.now(timezone.utc).isoformat()


def _event_ids_from_form(form_data):
    values = re.split(r"[\s,]+", " ".join(form_data.getlist("fis_event_ids")))
    return list(dict.fromkeys(int(value) for value in values if value.isdigit() and int(value) > 0))[:10]


class DemoSportsEditorialRepository:
    """Process-local pilot repository. Replace this implementation, not the views, for Supabase."""

    def __init__(self):
        self._lock = RLock()
        self.reset()

    def reset(self):
        with self._lock:
            self._submissions, self._entities = fresh_demo_data()
            self._fis_publications = {}
            self._result_imports, self._results = [], []

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
            "event_date": data.get("event_date", "").strip(), "fis_event_ids": data.get("fis_event_ids", []),
            "fis_external_id": build_fis_external_id(data), "author_name": data["author_name"].strip(),
            "author_email": data.get("author_email", "").strip(), "status": status, "editor_notes": "", "fis_submission_notes": "",
            "amp_id": data.get("amp_id", "").strip(), "client_name": data.get("client_name", "FIS").strip(),
            "publication_deadline": data.get("publication_deadline", ""), "researcher_deadline": data.get("researcher_deadline", ""),
            "researcher_user_id": data.get("researcher_user_id") or None, "researcher_name": data.get("researcher_name", ""),
            "sub_editor_user_id": data.get("sub_editor_user_id") or None, "sub_editor_name": data.get("sub_editor_name", ""),
            "working_notes": "", "unused_stats": "", "last_modified_by": data["author_name"].strip(),
            "created_at": now, "updated_at": now, "submitted_at": now if status == "submitted" else None, "approved_at": None,
            "stats": [{"id": str(uuid4()), "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "entity_ids": [], "entity_mentions": {}, "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()],
        }
        with self._lock:
            self._submissions.append(item)
        return deepcopy(item)

    def update_research(self, submission_id, form_data, submit=False):
        from .auth import current_user
        user = current_user() or {}
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            item["event_date"] = form_data.get("event_date", item.get("event_date", ""))
            item["working_notes"] = form_data.get("working_notes", "").strip()
            item["unused_stats"] = form_data.get("unused_stats", "").strip()
            blocks = []
            block_ids = form_data.getlist("content_id")
            for index, (kind, content) in enumerate(zip(form_data.getlist("content_type"), form_data.getlist("content_html"))):
                kind = "section" if kind == "heading" else kind
                if kind in ("stat", "section") and sanitise_rich_text(content).strip():
                    blocks.append({"id": block_ids[index] if index < len(block_ids) and block_ids[index] else str(uuid4()), "sort_order": index, "content_type": kind, "stat_text": sanitise_rich_text(content), "edited_text": "", "editor_comment": "", "entity_ids": [], "entity_mentions": {}, "tags": []})
            item["stats"] = blocks
            item["status"] = "submitted" if submit else "draft"
            item["submitted_at"] = _now() if submit else item.get("submitted_at")
            item["updated_at"] = _now()
            item["last_modified_by"] = user.get("full_name") or user.get("email") or "Workspace user"
            return deepcopy(item)

    def update_review(self, submission_id, form_data, requested_status):
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            item["editor_notes"] = form_data.get("editor_notes", "").strip()
            item["fis_submission_notes"] = form_data.get("fis_submission_notes", "").strip()
            item["fis_event_ids"] = _event_ids_from_form(form_data)
            for field in ("title", "amp_id", "client_name", "competition", "event_name", "gender", "location", "event_date", "publication_deadline", "researcher_deadline", "researcher_user_id", "researcher_name", "sub_editor_user_id", "sub_editor_name", "working_notes", "unused_stats"):
                if field in form_data:
                    item[field] = form_data.get(field, "").strip() or None
            demo_names = {"demo-user": "Jamie Laurent", "demo-researcher-2": "Andrew Hendry", "demo-sub-editor": "Nick L.", "demo-supervisor": "Supervisor Demo"}
            item["researcher_name"] = demo_names.get(item.get("researcher_user_id"), "Unassigned")
            item["sub_editor_name"] = demo_names.get(item.get("sub_editor_user_id"), "Unassigned")
            for stat in item["stats"]:
                stat_id = stat["id"]
                stat["edited_text"] = sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", ""))
                stat["editor_comment"] = form_data.get(f"editor_comment_{stat_id}", "").strip()
                stat["tags"] = [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()]
                allowed_ids = {entity["id"] for entity in self._entities}
                stat["entity_ids"] = [entity_id for entity_id in form_data.getlist(f"entity_ids_{stat_id}") if entity_id in allowed_ids]
                stat["entity_mentions"] = {
                    entity_id: form_data.get(f"entity_mention_{stat_id}_{entity_id}", "").strip()
                    for entity_id in stat["entity_ids"]
                    if form_data.get(f"entity_mention_{stat_id}_{entity_id}", "").strip()
                }
            item["status"] = requested_status
            item["updated_at"] = _now()
            from .auth import current_user
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

    def list_entities(self, entity_type="", limit=None):
        items = [item for item in self._entities if not entity_type or item["entity_type"] == entity_type]
        items = sorted(items, key=lambda item: (item["entity_type"], item["name"]))
        return deepcopy(items[:limit] if limit else items)

    def get_entities_by_ids(self, entity_ids):
        wanted = set(entity_ids)
        return deepcopy([item for item in self._entities if item["id"] in wanted])

    def search_entities(self, query, entity_type="", limit=10):
        needle = query.casefold().strip()
        matches = [
            entity for entity in self._entities
            if (not entity_type or entity["entity_type"] == entity_type)
            and (needle in entity["name"].casefold() or needle in entity.get("canonical_id", "").casefold())
        ]
        return deepcopy(sorted(matches, key=lambda item: (not item["name"].casefold().startswith(needle), item["name"]))[:limit])

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
        links = self.client.request("sports_editorial_stat_entities", query={"select": "stat_id,entity_id,relationship_type,mention_text", "stat_id": f"in.({','.join(stat_ids)})"}) if stat_ids else []
        entity_ids = {}
        entity_mentions = {}
        for link in links:
            entity_ids.setdefault(link["stat_id"], []).append(link["entity_id"])
            if link.get("mention_text"):
                entity_mentions.setdefault(link["stat_id"], {})[link["entity_id"]] = link["mention_text"]
        by_submission = {}
        for stat in stats:
            stat["entity_ids"] = entity_ids.get(stat["id"], [])
            stat["entity_mentions"] = entity_mentions.get(stat["id"], {})
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
            "event_date": data.get("event_date") or None, "fis_event_ids": data.get("fis_event_ids", []),
            "fis_external_id": build_fis_external_id(data), "author_name": data["author_name"].strip(), "author_email": data.get("author_email", "").strip(),
            "status": status, "editor_notes": "", "fis_submission_notes": "", "submitted_at": now if status == "submitted" else None,
            "amp_id": data.get("amp_id") or None, "client_name": data.get("client_name") or "FIS",
            "publication_deadline": data.get("publication_deadline") or None, "researcher_deadline": data.get("researcher_deadline") or None,
            "researcher_user_id": data.get("researcher_user_id") or None, "sub_editor_user_id": data.get("sub_editor_user_id") or None,
            "working_notes": "", "unused_stats": "", "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email"),
        }
        created = self.client.request("sports_editorial_submissions", "POST", payload=submission, prefer="return=representation")[0]
        blocks = [{"submission_id": created["id"], "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()]
        if blocks:
            self.client.request("sports_editorial_stats", "POST", payload=blocks, prefer="return=minimal")
        return self.get_submission(created["id"])

    def update_research(self, submission_id, form_data, submit=False):
        from .auth import current_user
        user = current_user() or {}
        now = _now()
        changes = {"event_date": form_data.get("event_date") or None, "working_notes": form_data.get("working_notes", "").strip(), "unused_stats": form_data.get("unused_stats", "").strip(), "status": "submitted" if submit else "draft", "updated_at": now, "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email")}
        if submit:
            changes["submitted_at"] = now
        self.client.request("sports_editorial_submissions", "PATCH", query={"id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}", "researcher_user_id": f"eq.{user.get('id')}"}, payload=changes, prefer="return=minimal")
        existing = self.get_submission(submission_id)
        for stat in existing.get("stats", []):
            self.client.request("sports_editorial_stats", "DELETE", query={"id": f"eq.{stat['id']}"})
        blocks = []
        block_ids = form_data.getlist("content_id")
        for index, (kind, content) in enumerate(zip(form_data.getlist("content_type"), form_data.getlist("content_html"))):
            kind = "section" if kind == "heading" else kind
            clean = sanitise_rich_text(content)
            if kind in ("stat", "section") and clean.strip():
                blocks.append({"id": block_ids[index] if index < len(block_ids) and block_ids[index] else str(uuid4()), "submission_id": submission_id, "sort_order": index, "content_type": kind, "stat_text": clean, "edited_text": "", "editor_comment": "", "tags": []})
        if blocks:
            self.client.request("sports_editorial_stats", "POST", payload=blocks, prefer="return=minimal")
        return self.get_submission(submission_id)

    def update_review(self, submission_id, form_data, requested_status):
        item = self.get_submission(submission_id)
        requested_entity_ids = [
            value for stat in item["stats"]
            for value in form_data.getlist(f"entity_ids_{stat['id']}")
        ]
        allowed_ids = {entity["id"] for entity in self.get_entities_by_ids(requested_entity_ids)}
        for stat in item["stats"]:
            stat_id = stat["id"]
            self.client.request("sports_editorial_stats", "PATCH", query={"id": f"eq.{stat_id}"}, payload={"edited_text": sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", "")), "editor_comment": form_data.get(f"editor_comment_{stat_id}", "").strip(), "tags": [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()], "updated_at": _now()}, prefer="return=minimal")
            selected = [value for value in form_data.getlist(f"entity_ids_{stat_id}") if value in allowed_ids]
            self.client.request("sports_editorial_stat_entities", "DELETE", query={"stat_id": f"eq.{stat_id}"})
            if selected:
                self.client.request("sports_editorial_stat_entities", "POST", payload=[{
                    "stat_id": stat_id, "entity_id": value,
                    "relationship_type": "inline" if form_data.get(f"entity_mention_{stat_id}_{value}", "").strip() else "about",
                    "mention_text": form_data.get(f"entity_mention_{stat_id}_{value}", "").strip() or None,
                } for value in selected], prefer="return=minimal")
        event_ids = _event_ids_from_form(form_data)
        from .auth import current_user
        user = current_user() or {}
        changes = {"status": requested_status, "editor_notes": form_data.get("editor_notes", "").strip(), "fis_submission_notes": form_data.get("fis_submission_notes", "").strip(), "fis_event_ids": event_ids, "updated_at": _now(), "last_modified_by_user_id": user.get("id"), "last_modified_by_name": user.get("full_name") or user.get("email")}
        for field in ("title", "amp_id", "client_name", "competition", "event_name", "gender", "location", "event_date", "publication_deadline", "researcher_deadline", "researcher_user_id", "sub_editor_user_id", "working_notes", "unused_stats"):
            if field in form_data:
                changes[field] = form_data.get(field) or None
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

    def search_entities(self, query, entity_type="", limit=10):
        params = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "name": f"ilike.*{query}*", "limit": str(limit), "order": "name.asc"}
        if entity_type:
            params["entity_type"] = f"eq.{entity_type}"
        matches = self.client.request("sports_editorial_entities", query=params)
        if len(matches) < limit:
            code_params = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "canonical_id": f"ilike.*{query}*", "limit": str(limit - len(matches)), "order": "name.asc"}
            if entity_type:
                code_params["entity_type"] = f"eq.{entity_type}"
            seen = {item["id"] for item in matches}
            matches.extend(item for item in self.client.request("sports_editorial_entities", query=code_params) if item["id"] not in seen)
        return matches[:limit]

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
        return self.client.request("sports_editorial_result_imports", query={
            "select": "*", "workspace_id": f"eq.{self._workspace()}", "order": "race_date.desc.nullslast", "limit": "1000",
        })

    def list_results(self, race_ids=None):
        query = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "order": "race_id.asc,place.asc.nullslast"}
        ids = list(dict.fromkeys(str(value) for value in (race_ids or []) if str(value).isdigit()))
        if ids:
            query["race_id"] = f"in.({','.join(ids)})"
        rows = []
        page_size = 1000
        for offset in range(0, 50000, page_size):
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
        current_codes = ",".join(str(row["fis_code"]) for row in payload)
        if current_codes:
            self.client.request("sports_editorial_results", "DELETE", query={
                "workspace_id": f"eq.{self._workspace()}", "race_id": f"eq.{record['race_id']}", "fis_code": f"not.in.({current_codes})",
            }, prefer="return=minimal")
        return len(payload)


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
        "result_status": row.get("status") or "finished", "total_time": row.get("time") or None,
        "diff_time": row.get("diff_time") or None, "fis_points": row.get("fis_points"), "cup_points": row.get("cup_points"),
        "source_url": row.get("source_url") or "", "imported_at": row.get("imported_at") or _now(),
    }


def _hydrate_result_row(row, imported):
    return {
        "race_id": str(row["race_id"]), "date": imported.get("race_date") or "", "venue": imported.get("venue") or "FIS event",
        "discipline": imported.get("event_code") or "AL", "gender": imported.get("gender") or "",
        "season_code": imported.get("season_code"),
        "competition": imported.get("category_code") or "FIS", "place": row.get("place"), "status": row.get("result_status"),
        "athlete": row.get("athlete_name"), "fis_code": str(row.get("fis_code") or ""),
        "competitor_id": str(row.get("competitor_id") or ""), "nation": row.get("nation_code"),
        "bib": str(row.get("bib") or ""), "birth_year": str(row.get("birth_year") or ""), "time": row.get("total_time") or "",
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
