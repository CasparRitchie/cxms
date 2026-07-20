from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from .demo_data import fresh_demo_data
from .formatting import sanitise_rich_text
from .validation import VALID_CONTENT_TYPES


def _now():
    return datetime.now(timezone.utc).isoformat()


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
            "fis_external_id": f"cxms-{uuid4()}", "author_name": data["author_name"].strip(),
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

    def list_entities(self):
        return deepcopy(sorted(self._entities, key=lambda item: (item["entity_type"], item["name"])))

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


repository = DemoSportsEditorialRepository()
