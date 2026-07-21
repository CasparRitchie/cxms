from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import os
import re

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

    def list_submissions(self, status="", sport="", order="newest"):
        items = self._submissions
        if status:
            items = [item for item in items if item["status"] == status]
        if sport:
            items = [item for item in items if item["sport"] == sport]
        items = sorted(items, key=lambda item: item.get("submitted_at") or item["created_at"], reverse=order != "oldest")
        return deepcopy(items)

    def get_submission(self, submission_id):
        item = next((item for item in self._submissions if item["id"] == submission_id), None)
        return deepcopy(item) if item else None

    def create_submission(self, data, status):
        now = _now()
        item = {
            "id": str(uuid4()), "title": data["title"].strip(), "sport": data.get("sport", "").strip() or "alpine_skiing",
            "competition": data.get("competition", "").strip(), "event_name": data.get("event_name", "").strip(),
            "gender": data.get("gender", "").strip().upper(), "location": data.get("location", "").strip(),
            "event_date": data.get("event_date", "").strip(), "fis_event_ids": data.get("fis_event_ids", []),
            "fis_external_id": build_fis_external_id(data), "author_name": data["author_name"].strip(),
            "author_email": data.get("author_email", "").strip(), "status": status, "editor_notes": "",
            "created_at": now, "updated_at": now, "submitted_at": now if status == "submitted" else None, "approved_at": None,
            "stats": [{"id": str(uuid4()), "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "entity_ids": [], "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()],
        }
        with self._lock:
            self._submissions.append(item)
        return deepcopy(item)

    def update_review(self, submission_id, form_data, requested_status):
        with self._lock:
            item = next(item for item in self._submissions if item["id"] == submission_id)
            item["editor_notes"] = form_data.get("editor_notes", "").strip()
            item["fis_event_ids"] = _event_ids_from_form(form_data)
            for stat in item["stats"]:
                stat_id = stat["id"]
                stat["edited_text"] = sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", ""))
                stat["editor_comment"] = form_data.get(f"editor_comment_{stat_id}", "").strip()
                stat["tags"] = [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()]
                allowed_ids = {entity["id"] for entity in self._entities}
                stat["entity_ids"] = [entity_id for entity_id in form_data.getlist(f"entity_ids_{stat_id}") if entity_id in allowed_ids]
            item["status"] = requested_status
            item["updated_at"] = _now()
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


class SupabaseSportsEditorialRepository:
    """Workspace-scoped persistence using the isolated sports_editorial_* tables."""

    def __init__(self, client=None):
        self.client = client or SupabaseRestClient()

    def reset(self):
        # Tests use the demo repository. Never delete shared Supabase data here.
        return None

    def _workspace(self):
        from .auth import current_user
        user = current_user()
        return user["workspace_id"] if user else ""

    def _hydrate(self, rows):
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        stats = self.client.request("sports_editorial_stats", query={"select": "*", "submission_id": f"in.({','.join(ids)})", "order": "sort_order.asc"})
        stat_ids = [row["id"] for row in stats]
        links = self.client.request("sports_editorial_stat_entities", query={"select": "stat_id,entity_id", "stat_id": f"in.({','.join(stat_ids)})"}) if stat_ids else []
        entity_ids = {}
        for link in links:
            entity_ids.setdefault(link["stat_id"], []).append(link["entity_id"])
        by_submission = {}
        for stat in stats:
            stat["entity_ids"] = entity_ids.get(stat["id"], [])
            by_submission.setdefault(stat["submission_id"], []).append(stat)
        for row in rows:
            row["stats"] = by_submission.get(row["id"], [])
        return rows

    def list_submissions(self, status="", sport="", order="newest"):
        query = {"select": "*", "workspace_id": f"eq.{self._workspace()}", "order": f"submitted_at.{'desc' if order != 'oldest' else 'asc'}.nullslast"}
        if status:
            query["status"] = f"eq.{status}"
        if sport:
            query["sport"] = f"eq.{sport}"
        return self._hydrate(self.client.request("sports_editorial_submissions", query=query))

    def get_submission(self, submission_id):
        rows = self.client.request("sports_editorial_submissions", query={"select": "*", "id": f"eq.{submission_id}", "workspace_id": f"eq.{self._workspace()}", "limit": "1"})
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
            "status": status, "editor_notes": "", "submitted_at": now if status == "submitted" else None,
        }
        created = self.client.request("sports_editorial_submissions", "POST", payload=submission, prefer="return=representation")[0]
        blocks = [{"submission_id": created["id"], "sort_order": index, "content_type": block["content_type"], "stat_text": sanitise_rich_text(block["content_html"]), "edited_text": "", "editor_comment": "", "tags": []} for index, block in enumerate(data["content"]) if block["content_type"] in VALID_CONTENT_TYPES and block["content_html"].strip()]
        if blocks:
            self.client.request("sports_editorial_stats", "POST", payload=blocks, prefer="return=minimal")
        return self.get_submission(created["id"])

    def update_review(self, submission_id, form_data, requested_status):
        item = self.get_submission(submission_id)
        allowed_ids = {entity["id"] for entity in self.list_entities()}
        for stat in item["stats"]:
            stat_id = stat["id"]
            self.client.request("sports_editorial_stats", "PATCH", query={"id": f"eq.{stat_id}"}, payload={"edited_text": sanitise_rich_text(form_data.get(f"edited_text_{stat_id}", "")), "editor_comment": form_data.get(f"editor_comment_{stat_id}", "").strip(), "tags": [tag.strip().lower() for tag in form_data.get(f"tags_{stat_id}", "").split(",") if tag.strip()], "updated_at": _now()}, prefer="return=minimal")
            selected = [value for value in form_data.getlist(f"entity_ids_{stat_id}") if value in allowed_ids]
            self.client.request("sports_editorial_stat_entities", "DELETE", query={"stat_id": f"eq.{stat_id}"})
            if selected:
                self.client.request("sports_editorial_stat_entities", "POST", payload=[{"stat_id": stat_id, "entity_id": value} for value in selected], prefer="return=minimal")
        event_ids = _event_ids_from_form(form_data)
        changes = {"status": requested_status, "editor_notes": form_data.get("editor_notes", "").strip(), "fis_event_ids": event_ids, "updated_at": _now()}
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


def _build_repository():
    if os.getenv("SPORTS_EDITORIAL_REPOSITORY", "demo").strip().lower() == "supabase":
        client = SupabaseRestClient()
        if client.configured:
            return SupabaseSportsEditorialRepository(client)
    return DemoSportsEditorialRepository()


repository = _build_repository()
