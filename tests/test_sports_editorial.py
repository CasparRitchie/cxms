import json
import unittest

from app import app
from services.sports_editorial.demo_data import fresh_demo_data
from services.sports_editorial.json_export import build_pilot_export
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
        errors = validate_submission({"title": "", "author_name": "", "stats": [""]}, submitting=True)
        self.assertEqual(len(errors), 3)
        self.assertEqual(validate_submission({"title": "Pack", "author_name": "Jamie", "stats": ["One fact"]}, submitting=True), [])

    def test_status_transition_validation(self):
        self.assertTrue(validate_status_transition("submitted", "approved")[0])
        self.assertFalse(validate_status_transition("draft", "approved")[0])
        self.assertFalse(validate_status_transition("submitted", "made_up")[0])

    def test_json_transformation_prefers_edited_text_and_links_entities(self):
        submissions, entities = fresh_demo_data()
        payload = build_pilot_export(submissions[2], {item["id"]: item for item in entities})
        self.assertEqual(payload["schema_version"], "pilot-1.0")
        self.assertTrue(payload["stats"][0]["text"].startswith("Noa Martin earned"))
        self.assertEqual(payload["stats"][0]["entities"][0]["type"], "athlete")

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
            "event_name": "Demo downhill", "event_date": "2026-12-12", "author_name": "Journalist Demo",
            "author_email": "journalist@example.com", "stats": ["First demonstration fact.", "Second demonstration fact."],
            "action": "submit",
        })
        self.assertEqual(response.status_code, 302)
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.assertEqual(repository.get_submission(submission_id)["status"], "submitted")

        self.set_sub_editor()
        first_stat = repository.get_submission(submission_id)["stats"][0]
        response = self.client.post(f"/workspace/sports-editorial/submissions/{submission_id}", data={
            "status": "approved", "editor_notes": "Approved for demo.",
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

    def test_journalist_cannot_change_editorial_status(self):
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={"status": "approved"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
