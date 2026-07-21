import json
import os
import unittest
from unittest.mock import patch

from app import app
from services.sports_editorial.demo_data import fresh_demo_data
from services.sports_editorial.json_export import build_pilot_export
from services.sports_editorial.formatting import sanitise_rich_text
from services.sports_editorial.fis_client import FisApiError, get_fis_client
from services.sports_editorial.fis_export import build_fis_payload
from services.sports_editorial.identifiers import build_fis_external_id
from services.sports_editorial.repository import repository
from services.sports_editorial.validation import validate_status_transition, validate_submission


class SportsEditorialPilotTests(unittest.TestCase):
    def setUp(self):
        repository.reset()
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def set_sub_editor(self):
        with self.client.session_transaction() as session:
            session["sports_editorial_role"] = "sub_editor"

    def test_submission_validation(self):
        errors = validate_submission({"title": "", "content": [{"content_type": "stat", "content_html": ""}]}, submitting=True)
        self.assertEqual(len(errors), 3)
        self.assertEqual(validate_submission({"title": "Pack", "fis_event_ids": [12345], "content": [{"content_type": "stat", "content_html": "One fact"}]}, submitting=True), [])
        self.assertIn("Alpine Skiing", validate_submission({"title": "Pack", "sport": "ski_jumping", "content": [{"content_type": "stat", "content_html": "One fact"}]})[0])

    def test_readable_amp_external_id(self):
        self.assertEqual(build_fis_external_id({"gender": "W", "event_name": "Giant Slalom", "location": "Val d’Isère", "event_date": "2026-10-27"}), "amp-alp-w-giant-slalom-val-disere-2026")

    def test_rich_text_sanitisation(self):
        self.assertEqual(sanitise_rich_text('<strong>Safe</strong><script>alert(1)</script><a href="bad"> link</a>'), "<strong>Safe</strong>alert(1) link")

    def test_status_transition_validation(self):
        self.assertTrue(validate_status_transition("submitted", "approved")[0])
        self.assertFalse(validate_status_transition("draft", "approved")[0])
        self.assertFalse(validate_status_transition("submitted", "made_up")[0])

    def test_json_transformation_prefers_edited_text_and_links_entities(self):
        submissions, entities = fresh_demo_data()
        payload = build_pilot_export(submissions[0], {item["id"]: item for item in entities})
        self.assertEqual(payload["schema_version"], "pilot-1.0")
        self.assertEqual(payload["submission"]["event"]["gender"], "W")
        self.assertEqual(payload["stats"][0]["type"], "section")
        self.assertEqual(payload["stats"][1]["entities"][0]["type"], "athlete")

    def test_smoke_routes(self):
        paths = [
            "/", "/games", "/circuit-training", "/gcse/history", "/football", "/data-explorer",
            "/sports-editorial", "/workspace/sports-editorial", "/workspace/sports-editorial/", "/workspace/sports-editorial/submit",
            "/workspace/sports-editorial/queue",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_create_review_approve_and_download_workflow(self):
        response = self.client.post("/workspace/sports-editorial/submit", data={
            "title": "Tomorrow demo pack", "sport": "alpine_skiing", "competition": "FIS Demo Cup",
            "event_name": "Demo downhill", "gender": "W", "location": "Kronplatz", "event_date": "2026-12-12",
            "fis_event_ids": "55596",
            "content_type": ["section", "stat", "stat"], "content_html": ["Previous race", "<strong>First</strong> demonstration fact.", "Second demonstration fact."],
            "action": "submit",
        })
        self.assertEqual(response.status_code, 302)
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.assertEqual(repository.get_submission(submission_id)["status"], "submitted")

        self.set_sub_editor()
        first_stat = repository.get_submission(submission_id)["stats"][0]
        response = self.client.post(f"/workspace/sports-editorial/submissions/{submission_id}", data={
            "status": "approved", "editor_notes": "Approved for demo.",
            "fis_event_ids": "55596",
            f"edited_text_{first_stat['id']}": "First edited demonstration fact.",
            f"entity_ids_{first_stat['id']}": "entity-athlete-lena",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(repository.get_submission(submission_id)["status"], "approved")

        download = self.client.get(f"/workspace/sports-editorial/exports/{submission_id}.json")
        self.assertEqual(download.status_code, 200)
        payload = json.loads(download.data)
        self.assertEqual(payload["stats"][0]["text"], "First edited demonstration fact.")

    def test_unapproved_download_is_forbidden(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/exports/demo-submission-submitted.json")
        self.assertEqual(response.status_code, 403)

    def test_entity_autocomplete_search(self):
        response = self.client.get("/workspace/sports-editorial/entities/search?q=cam&type=athlete")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["provider"], "local_pilot")
        self.assertEqual(payload["results"][0]["canonical_id"], "demo-athlete-rast")

        invalid = self.client.get("/workspace/sports-editorial/entities/search?q=cam&type=invalid")
        self.assertEqual(invalid.status_code, 400)

    def test_fis_payload_matches_v1_shape(self):
        submissions, entities = fresh_demo_data()
        payload = build_fis_payload(submissions[0], {item["id"]: item for item in entities})
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["disciplineCode"], "AL")
        self.assertEqual(payload["eventIds"], [55596])
        self.assertEqual(payload["sections"][0]["genderCode"], "W")
        self.assertNotIn("<strong>", payload["sections"][0]["items"][0]["text"])
        self.assertEqual(payload["sections"][0]["items"][0]["links"][0]["type"], "athlete")
        self.assertIn("previous-competition", payload["sections"][0]["items"][0]["tags"])

    def test_mock_fis_publish_and_withdraw(self):
        self.set_sub_editor()
        preview = self.client.get("/workspace/sports-editorial/submissions/demo-submission-approved/fis-preview")
        self.assertEqual(preview.status_code, 200)
        self.assertIn(b'&#34;schemaVersion&#34;: 1', preview.data)

        published = self.client.post("/workspace/sports-editorial/submissions/demo-submission-approved/fis-publish")
        self.assertEqual(published.status_code, 302)
        state = repository.get_fis_publication("demo-submission-approved")
        self.assertEqual(state["status"], "published")
        self.assertEqual(state["version"], 1)

        self.client.post("/workspace/sports-editorial/submissions/demo-submission-approved/fis-publish")
        unchanged = repository.get_fis_publication("demo-submission-approved")
        self.assertEqual(unchanged["version"], 1)
        self.assertTrue(unchanged["unchanged"])

        withdrawn = self.client.post("/workspace/sports-editorial/submissions/demo-submission-approved/fis-withdraw")
        self.assertEqual(withdrawn.status_code, 302)
        self.assertEqual(repository.get_fis_publication("demo-submission-approved")["status"], "withdrawn")

    def test_unapproved_submission_cannot_publish_to_fis(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted/fis-publish")
        self.assertEqual(response.status_code, 403)

    def test_live_fis_mode_requires_configuration(self):
        with patch.dict(os.environ, {"FIS_API_MODE": "live", "FIS_API_BASE_URL": "", "FIS_API_TOKEN": ""}, clear=False):
            with self.assertRaises(FisApiError):
                get_fis_client()

    def test_live_fis_mode_remains_safety_locked(self):
        with patch.dict(os.environ, {"FIS_API_MODE": "live", "FIS_API_BASE_URL": "https://fis.invalid", "FIS_API_TOKEN": "test", "FIS_LIVE_PUBLISH_ENABLED": "false", "FIS_SAFE_EVENT_IDS": "55596"}, clear=False):
            client = get_fis_client()
            with self.assertRaises(FisApiError) as context:
                client.publish("amp-alp-w-test-place-2026", {"eventIds": [55596]})
            self.assertEqual(context.exception.status_code, 503)

    def test_journalist_cannot_change_editorial_status(self):
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={"status": "approved"})
        self.assertEqual(response.status_code, 403)

    def test_review_rejects_non_numeric_fis_event_id(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={"status": "submitted", "fis_event_ids": "DemoCalendarID00001x"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"must contain digits only", response.data)
        self.assertEqual(repository.get_submission("demo-submission-submitted")["fis_event_ids"], [55596])

    def test_publication_wording_is_editable_for_sub_editor(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'contenteditable="true"', response.data)
        self.assertIn(b'aria-label="Publication wording"', response.data)


if __name__ == "__main__":
    unittest.main()
