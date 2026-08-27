import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from app import app
from services.sports_editorial.demo_data import fresh_demo_data
from services.sports_editorial.json_export import build_pilot_export
from services.sports_editorial.formatting import sanitise_rich_text
from services.sports_editorial.fis_client import FisApiError, LiveFisClient, get_fis_client
from services.sports_editorial.fis_export import FisPayloadValidationError, build_fis_payload
from services.sports_editorial.fis_calendar import parse_calendar_events
from services.sports_editorial.fis_athletes import parse_athlete_csv
from services.sports_editorial.fis_entities import countries_from_athletes, parse_event_competitions
from services.sports_editorial.fis_results import parse_fis_results
from services.sports_editorial.identifiers import build_fis_external_id
from services.sports_editorial.repository import SupabaseSportsEditorialRepository, repository
from services.sports_editorial.stat_insights import build_editorial_discoveries, build_perspective_insights, build_stat_insights, demo_result_rows, group_editorial_discoveries
from services.sports_editorial.validation import validate_status_transition, validate_submission
from services.sports_editorial.creation import parse_display_date
from services.sports_editorial import views as sports_editorial_views
from services.sports_editorial.formatting import render_entity_links


class SportsEditorialPilotTests(unittest.TestCase):
    def setUp(self):
        repository.reset()
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def set_sub_editor(self):
        with self.client.session_transaction() as session:
            session["sports_editorial_role"] = "sub_editor"

    def set_role(self, role):
        with self.client.session_transaction() as session:
            session["sports_editorial_role"] = role

    def valid_creation(self, **overrides):
        data = {
            "title": "Creation test", "sport": "alpine_skiing", "competition": "FIS World Cup",
            "event_name": "Giant Slalom", "season_code": "2026", "calendar_event_id": "55596",
            "fis_event_ids": "55596", "content_type": "", "content_html": "", "action": "draft",
        }
        data.update(overrides)
        return data

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
        self.assertEqual(payload["schema_version"], "pilot-1.1")
        self.assertEqual(payload["submission"]["event"]["gender"], "W")
        self.assertEqual(payload["submission"]["fis"]["event_ids"], [55596])
        self.assertEqual(payload["stats"][0]["type"], "section")
        self.assertEqual(payload["stats"][1]["entities"][0]["type"], "athlete")
        self.assertEqual(payload["stats"][1]["entities"][0]["fis_reference"]["type"], "athlete")

    def test_smoke_routes(self):
        paths = [
            "/", "/games", "/circuit-training", "/level-crossing", "/gcse/history", "/football", "/data-explorer",
            "/sports-editorial", "/workspace/sports-editorial", "/workspace/sports-editorial/", "/workspace/sports-editorial/submit",
            "/workspace/sports-editorial/queue", "/workspace/sports-editorial/stat-insights",
        ]
        for path in paths:
            with self.subTest(path=path):
                expected = 403 if path == "/workspace/sports-editorial/submit" else (302 if path in ("/workspace/sports-editorial", "/workspace/sports-editorial/") else 200)
                self.assertEqual(self.client.get(path).status_code, expected)

    def test_stat_insights_calculate_venue_totals_and_streaks(self):
        insights = build_stat_insights(demo_result_rows(), venue="Kronplatz", discipline="GS")
        self.assertEqual(insights["race_count"], 5)
        self.assertEqual(insights["leaders"][0]["athlete"], "Mikaela Shiffrin")
        self.assertEqual(insights["leaders"][0]["wins"], 3)
        self.assertGreaterEqual(insights["streaks"][0]["podium_streak"], 3)
        self.assertTrue(insights["discoveries"])

    def test_editorial_discovery_surfaces_explainable_outliers_and_trends(self):
        rows = [
            {"date": f"2026-01-0{index}", "venue": "A", "discipline": "GS", "athlete": "Leader", "nation": "SUI", "place": place}
            for index, place in enumerate([6, 5, 2, 1], 1)
        ] + [
            {"date": f"2026-01-0{index}", "venue": "B", "discipline": "GS", "athlete": "Peer", "nation": "AUT", "place": place}
            for index, place in enumerate([8, 7, 6, 5], 1)
        ]
        discoveries = build_editorial_discoveries(rows)
        self.assertTrue(any(item["kind"] == "trend" and "Leader" in item["title"] for item in discoveries))
        self.assertTrue(all(item.get("evidence") for item in discoveries))

    def test_research_leads_are_grouped_with_independent_quotas_and_empty_states(self):
        candidates = [{"label": "Emerging trend", "title": f"Trend {index}", "score": 10 - index} for index in range(8)]
        candidates += [{"label": "Venue specialist", "title": "Venue one", "score": 1}]
        groups = group_editorial_discoveries(candidates)
        self.assertEqual([group["label"] for group in groups], ["Performance outlier", "Emerging trend", "Venue specialist", "Experience group"])
        self.assertEqual(len(groups[1]["items"]), 4)
        self.assertEqual(len(groups[2]["items"]), 1)
        self.assertEqual(groups[0]["items"], [])

    def test_additional_perspectives_cover_country_time_gender_and_age(self):
        rows = []
        for index, (gender, host) in enumerate((("W", "SUI"), ("M", "AUT"))):
            for race_number in range(3):
                common = {"race_id": f"{index + 1}{race_number}", "date": f"2025-01-0{race_number + 1}",
                          "venue": host, "host_nation": host, "discipline": "GS", "gender": gender, "status": "finished"}
                rows.extend([
                    {**common, "athlete": f"Winner {gender}", "fis_code": f"1{index}", "birth_year": "1990", "nation": host, "place": 1, "time": "1:30.00"},
                    {**common, "athlete": f"Second {gender}", "fis_code": f"2{index}", "birth_year": "1995", "nation": host, "place": 2, "time": "1:30.20"},
                    {**common, "athlete": f"Third {gender}", "fis_code": f"3{index}", "birth_year": "2000", "nation": host, "place": 3, "time": "1:30.50"},
                ])
        groups = build_perspective_insights(rows)
        by_label = {group["label"]: group["items"] for group in groups}
        self.assertTrue(by_label["Country patterns"])
        self.assertTrue(by_label["Time and margins"])
        self.assertTrue(by_label["Women and men"])
        self.assertTrue(by_label["Age milestones"])

    def test_stat_insights_page_explains_demo_data_and_filters(self):
        response = self.client.get("/workspace/sports-editorial/stat-insights?venue=Kronplatz")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Demonstration data", response.data)
        self.assertIn(b"Mikaela Shiffrin", response.data)
        self.assertIn(b"Confirmed facts", response.data)
        self.assertIn(b"Pre-race scenarios", response.data)
        self.assertIn(b"currently loaded results only", response.data)
        self.assertIn(b"Scenario athlete FIS codes", response.data)

    def test_stored_official_results_replace_demo_default_and_show_coverage(self):
        race = {"canonical_id": "127367", "canonical_url": "https://www.fis-ski.com/result",
                "metadata": {"season_code": 2026, "event_id": "55595", "category_code": "WC"}}
        rows = [{"race_id": "127367", "date": "2026-01-03", "venue": "Kranjska Gora", "discipline": "GS",
                 "gender": "W", "competition": "WC", "place": 1, "status": "finished", "athlete": "RAST Camille",
                 "fis_code": "516562", "competitor_id": "203812", "nation": "SUI", "bib": "1", "birth_year": "1999",
                 "time": "2:00.09", "source_url": race["canonical_url"], "source": "fis_official_results", "imported_at": "2026-07-22T10:00:00+00:00"}]
        repository.save_result_import(race, rows)
        response = self.client.get("/workspace/sports-editorial/stat-insights")
        self.assertIn(b"Stored official FIS result data", response.data)
        self.assertIn(b"127367", response.data)
        self.assertNotIn(b"Alice Robinson", response.data)
        scenario = self.client.get("/workspace/sports-editorial/stat-insights?scenario_athlete_ids=516562")
        self.assertIn(b"A win for RAST Camille", scenario.data)
        self.assertIn(b"A podium for RAST Camille", scenario.data)
        self.assertIn(b"conditional", scenario.data)

    def test_controlled_import_is_missing_only_and_capped(self):
        self.set_role("supervisor")
        repository.upsert_entities([{"entity_type": "competition", "name": "GS W test", "canonical_id": "127367",
                                     "canonical_url": "https://www.fis-ski.com/result", "country_code": "SLO",
                                     "metadata": {"season_code": 2026, "event_id": "55595", "category_code": "WC", "date": "2026-01-03"}}])
        rows = [{"race_id": "127367", "date": "2026-01-03", "venue": "Kranjska Gora", "discipline": "GS",
                 "gender": "W", "competition": "WC", "place": 1, "status": "finished", "athlete": "RAST Camille",
                 "fis_code": "516562", "competitor_id": "203812", "nation": "SUI", "bib": "1", "birth_year": "1999",
                 "time": "2:00.09", "source_url": "https://www.fis-ski.com/result", "imported_at": "2026-07-22T10:00:00+00:00"}]
        with patch("services.sports_editorial.views.fetch_alpine_results", return_value=(rows, 0)) as fetch:
            response = self.client.post("/workspace/sports-editorial/stat-insights/import", data={"season": "2026", "limit": "99"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(len(fetch.call_args.args[0]), 1)
            self.assertEqual(fetch.call_args.kwargs["request_interval"], 1.5)
        with patch("services.sports_editorial.views.fetch_alpine_results") as fetch_again:
            self.client.post("/workspace/sports-editorial/stat-insights/import", data={"season": "2026"})
            fetch_again.assert_not_called()

    def test_official_fis_result_parser_retains_provenance_and_non_finishers(self):
        html = '''
        <h1 class="heading">Kranjska Gora (SLO)</h1>
        <div data-formatted-date="January 03, 2026">January 03, 2026</div>
        <option value="127367" selected>03.01.2026 - Women's Giant Slalom | WC</option>
        <a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=203812">
          <div class="g-lg-1 pr-1 bold justify-right">1</div><div class="g-lg-1 gray justify-center">1</div>
          <div class="g-lg-2 pr-1 gray justify-right">516562</div><div class="g-lg-4 bold justify-left">RAST Camille</div>
          <div class="g-lg-1 hidden-sm-down justify-left">1999</div><span class="country__name-short">SUI</span>
          <div class="g-lg-2 blue bold justify-right">2:00.09</div>
        </a>
        <div class="g-xs-24 bold">Did not finish 1st run</div>
        <a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=221779">
          <div class="g-lg-1 pr-1 bold justify-right"></div><div class="g-lg-1 gray justify-center">4</div>
          <div class="g-lg-2 pr-1 gray justify-right">415232</div><div class="g-lg-4 bold justify-left">ROBINSON Alice</div>
          <div class="g-lg-1 hidden-sm-down justify-left">2001</div><span class="country__name-short">NZL</span>
        </a>'''
        rows = parse_fis_results(html, {"canonical_id": "127367", "canonical_url": "https://www.fis-ski.com/result"})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["discipline"], "GS")
        self.assertEqual(rows[0]["competition"], "WC")
        self.assertEqual(rows[0]["fis_code"], "516562")
        self.assertEqual(rows[1]["status"], "did_not_finish")
        self.assertEqual(rows[1]["place"], None)

    def test_researcher_cannot_create_or_open_unassigned_sheet(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data={
            **self.valid_creation(title="Unassigned researcher test", event_name="Slalom"),
            "gender": "W",
            "researcher_user_id": "demo-researcher-2", "content_type": "", "content_html": "",
            "action": "draft",
        })
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.set_role("researcher")
        self.assertEqual(self.client.get("/workspace/sports-editorial/submit").status_code, 403)
        self.assertEqual(self.client.get(f"/workspace/sports-editorial/submissions/{submission_id}").status_code, 404)
        self.assertNotIn(b"Unassigned researcher test", self.client.get("/workspace/sports-editorial/queue").data)

    def test_researcher_edits_assigned_in_progress_sheet_then_is_locked(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data={
            **self.valid_creation(title="Assigned sheet", event_name="Downhill"),
            "gender": "M", "event_date": "12-Oct-2026",
            "researcher_user_id": "demo-user", "sub_editor_user_id": "demo-sub-editor",
            "content_type": "", "content_html": "", "action": "draft",
        })
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.set_role("researcher")
        entry_page = self.client.get(f"/workspace/sports-editorial/submissions/{submission_id}/research")
        self.assertEqual(entry_page.status_code, 200)
        self.assertIn(b'class="sew-stats-builder" data-stats-list', entry_page.data)
        saved = self.client.post(f"/workspace/sports-editorial/submissions/{submission_id}/research", data={
            "event_date": "13-Oct-2026", "content_type": ["section", "stat"],
            "content_html": ["Race scenarios", "A researched statistic."],
            "working_notes": "Source: internal workbook", "unused_stats": "Reserve statistic", "action": "submit",
        })
        self.assertEqual(saved.status_code, 302)
        sheet = repository.get_submission(submission_id)
        self.assertEqual(sheet["status"], "submitted")
        self.assertEqual(sheet["season_code"], 2026)
        self.assertEqual(sheet["event_date"], "2026-10-13")
        self.assertEqual([block["content_type"] for block in sheet["stats"]], ["section", "stat"])
        self.assertEqual(self.client.get(f"/workspace/sports-editorial/submissions/{submission_id}/research").status_code, 403)
        exported = build_pilot_export(sheet, {})
        self.assertNotIn("working_notes", json.dumps(exported))
        self.assertNotIn("unused_stats", json.dumps(exported))

    def test_research_submit_button_value_is_preserved_by_browser_guard(self):
        script = Path("static/js/sports-editorial-submit.js").read_text(encoding="utf-8")
        self.assertIn("if (!event.submitter || formSubmitting)", script)
        self.assertIn("if (button !== event.submitter) button.disabled = true", script)
        self.assertNotIn(
            'form.querySelectorAll("button[type=\'submit\']").forEach((button) => { button.disabled = true; })',
            script,
        )

    def test_supervisor_has_editor_creation_access(self):
        self.set_role("supervisor")
        self.assertEqual(self.client.get("/workspace/sports-editorial/submit").status_code, 200)

    def test_fresh_creation_form_is_blank_and_has_no_suggestions(self):
        self.set_sub_editor()
        page = self.client.get("/workspace/sports-editorial/submit")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Controlled creation", page.data)
        self.assertNotIn(b"placeholder=", page.data)
        self.assertNotIn(b'name="client_name" value="FIS" checked', page.data)
        self.assertIn(b'name="title" required value=""', page.data)
        self.assertIn(b'name="season_code" required', page.data)
        self.assertIn(b'name="fis_event_ids" value="" readonly', page.data)
        self.assertEqual(page.data.count(b"data-date-picker"), 3)
        for label in (b"Choose race date", b"Choose researcher deadline", b"Choose publication deadline"):
            self.assertIn(label, page.data)

    def test_creation_required_fields_reject_blank_and_whitespace(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data={
            "title": " ", "sport": " ", "competition": " ", "season_code": " ",
        }, follow_redirects=True)
        for message in (b"Title is required", b"Sport is required", b"Competition is required", b"Season must be a four-digit year"):
            self.assertIn(message, response.data)
        self.assertEqual(len(repository.list_submissions()), 3)

    def test_creation_rejects_invalid_choice_combinations(self):
        self.set_sub_editor()
        for changes in (
            {"sport": "ski_jumping"},
            {"competition": "Invented Cup"},
            {"event_name": "Ski Cross"},
        ):
            with self.subTest(changes=changes):
                response = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(**changes), follow_redirects=True)
                self.assertIn(b"Select", response.data)
                self.assertEqual(len(repository.list_submissions()), 3)

    def test_valid_alpine_world_cup_creation_redirects_and_allocates_amp_id(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/confirmation/", response.headers["Location"])
        created = repository.list_submissions()[0]
        self.assertEqual(created["competition"], "FIS World Cup")
        self.assertEqual(created["event_name"], "Giant Slalom")
        self.assertEqual(created["amp_id"], "560004")

    def test_creation_dates_are_strict_and_persist_as_iso(self):
        self.assertEqual(parse_display_date("01-aUg-2026", "Race Date"), ("2026-08-01", None))
        for invalid in ("01/08/2026", "31-Feb-2026", "2026-08-01"):
            self.assertIsNotNone(parse_display_date(invalid, "Race Date")[1])
        self.set_sub_editor()
        bad = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(event_date="01/08/2026"), follow_redirects=True)
        self.assertIn(b"Race Date", bad.data)
        self.assertIn(b'value="01/08/2026"', bad.data)
        good = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(
            event_date="03-Aug-2026", researcher_deadline="31-Jul-2026", publication_deadline="01-Aug-2026",
        ))
        self.assertEqual(good.status_code, 302)
        created = repository.list_submissions()[0]
        self.assertEqual((created["event_date"], created["researcher_deadline"], created["publication_deadline"]),
                         ("2026-08-03", "2026-07-31", "2026-08-01"))

    def test_creation_resolves_canonical_location_and_rejects_forgery(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(
            location="Forged", fis_event_ids="99999",
        ))
        self.assertEqual(response.status_code, 302)
        created = repository.list_submissions()[0]
        self.assertEqual(created["location"], "Kronplatz")
        self.assertEqual(created["fis_event_ids"], [55596])
        unknown = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(
            calendar_event_id="99999", fis_event_ids="99999",
        ), follow_redirects=True)
        self.assertIn(b"known Client Event ID", unknown.data)

    def test_creation_rejects_amp_id_override(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data=self.valid_creation(amp_id="999999"), follow_redirects=True)
        self.assertIn(b"cannot be supplied", response.data)
        self.assertEqual(len(repository.list_submissions()), 3)

    def test_demo_test_users_do_not_leak_into_authenticated_mode(self):
        demo_names = {user["full_name"] for user in sports_editorial_views._assignment_users()}
        self.assertTrue({"Test User 1", "Test User 2"} <= demo_names)
        with patch.object(sports_editorial_views, "auth_configuration", return_value={"mode": "workspace"}), \
             patch.object(sports_editorial_views, "current_user", return_value={"workspace_id": "workspace"}), \
             patch.object(sports_editorial_views, "list_workspace_users", return_value=[]):
            self.assertEqual(sports_editorial_views._assignment_users(), [])

    def test_create_review_approve_and_download_workflow(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submit", data={
            **self.valid_creation(title="Tomorrow demo pack", event_name="Downhill"),
            "gender": "W", "event_date": "12-Dec-2026",
            "content_type": ["section", "stat", "stat"], "content_html": ["Previous race", "<strong>First</strong> demonstration fact.", "Second demonstration fact."],
            "action": "submit",
        })
        self.assertEqual(response.status_code, 302)
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.assertEqual(repository.get_submission(submission_id)["status"], "submitted")

        self.set_sub_editor()
        blocks = repository.get_submission(submission_id)["stats"]
        first_stat = blocks[0]
        review_data = {
            "status": "approved", "editor_notes": "Approved for demo.",
            "fis_event_ids": "55596",
            f"edited_text_{first_stat['id']}": "First edited demonstration fact.",
            f"entity_ids_{first_stat['id']}": "entity-athlete-rast",
        }
        review_data.update({f"accepted_{block['id']}": "1" for block in blocks})
        response = self.client.post(f"/workspace/sports-editorial/submissions/{submission_id}", data=review_data)
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
        self.assertEqual(payload["results"][0]["canonical_id"], "516562")
        self.assertEqual(payload["results"][0]["name"], "Camille Rast")

        invalid = self.client.get("/workspace/sports-editorial/entities/search?q=cam&type=invalid")
        self.assertEqual(invalid.status_code, 400)

        by_code = self.client.get("/workspace/sports-editorial/entities/search?q=SUI&type=country").get_json()
        by_name = self.client.get("/workspace/sports-editorial/entities/search?q=Switzerland&type=country").get_json()
        self.assertEqual(by_code["results"][0]["id"], by_name["results"][0]["id"])
        self.assertEqual(by_code["results"][0], {
            "id": "entity-country-ch",
            "type": "country",
            "name": "Switzerland",
            "canonical_id": "SUI",
            "canonical_url": "",
            "country_code": "SUI",
            "ski_sponsor": None,
        })

    def test_supabase_entity_search_includes_country_code_and_ranks_exact_matches(self):
        switzerland = {
            "id": "country-sui", "entity_type": "country", "name": "Switzerland",
            "canonical_id": "SUI", "country_code": "SUI", "canonical_url": None,
        }

        class SearchClient:
            def __init__(self):
                self.queries = []

            def request(self, table, query=None):
                self.queries.append(query)
                return [switzerland]

        client = SearchClient()
        supabase_repository = SupabaseSportsEditorialRepository(client=client, workspace_id="workspace")
        self.assertEqual(supabase_repository.search_entities("SUI", entity_type="country")[0]["id"], "country-sui")
        self.assertEqual(supabase_repository.search_entities("Switzerland", entity_type="country")[0]["id"], "country-sui")
        self.assertTrue(all("country_code.ilike." in query["or"] for query in client.queries))

    def test_country_mention_text_saves_code_or_full_name(self):
        for mention in ("SUI", "Switzerland"):
            with self.subTest(mention=mention):
                repository.reset()
                submission = repository.get_submission("demo-submission-kronplatz")
                block = next(item for item in submission["stats"] if item["content_type"] == "stat")
                form = MultiDict([
                    ("event_date", submission["event_date"]),
                    ("content_id", block["id"]),
                    ("content_type", "stat"),
                    ("content_html", f"Camille Rast represents {mention}."),
                    (f"entity_ids_{block['id']}", "entity-country-ch"),
                    (f"entity_mention_{block['id']}_entity-country-ch", mention),
                ])
                with app.test_request_context("/"), patch(
                    "services.sports_editorial.auth.current_user",
                    return_value={"id": "demo-user", "full_name": "Jamie Laurent", "role": "researcher"},
                ):
                    updated = repository.update_research(submission["id"], form)
                saved = updated["stats"][0]
                self.assertEqual(saved["entity_mentions"]["entity-country-ch"], mention)
                self.assertIn(mention, saved["stat_text"])

    def test_country_mention_text_saves_during_sub_edit(self):
        submission = repository.get_submission("demo-submission-submitted")
        block = next(item for item in submission["stats"] if item["content_type"] == "stat")
        form = MultiDict([
            ("content_id", block["id"]),
            ("content_type", "stat"),
            (f"edited_text_{block['id']}", "Camille Rast represents Switzerland."),
            (f"entity_ids_{block['id']}", "entity-country-ch"),
            (f"entity_mention_{block['id']}_entity-country-ch", "Switzerland"),
        ])
        with app.test_request_context("/"), patch(
            "services.sports_editorial.auth.current_user",
            return_value={"id": "demo-sub-editor", "full_name": "Nick L.", "role": "sub_editor"},
        ):
            updated = repository.update_review(submission["id"], form, "in_review")
        self.assertEqual(
            updated["stats"][0]["entity_mentions"]["entity-country-ch"],
            "Switzerland",
        )

    def test_deleted_linked_wording_removes_research_entity_relationship(self):
        submission = repository.get_submission("demo-submission-kronplatz")
        block = next(item for item in submission["stats"] if item["content_type"] == "stat")
        form = MultiDict([
            ("content_id", block["id"]),
            ("content_type", "stat"),
            ("content_html", "The athlete won the race."),
            (f"entity_ids_{block['id']}", "entity-athlete-rast"),
            (f"entity_mention_{block['id']}_entity-athlete-rast", "Camille Rast"),
        ])
        with app.test_request_context("/"), patch(
            "services.sports_editorial.auth.current_user",
            return_value={"id": "demo-user", "full_name": "Jamie Laurent", "role": "researcher"},
        ):
            updated = repository.update_research(submission["id"], form)
        self.assertEqual(updated["stats"][0]["entity_ids"], [])
        self.assertEqual(updated["stats"][0]["entity_mentions"], {})

    def test_deleted_linked_wording_removes_sub_edit_entity_relationship(self):
        submission = repository.get_submission("demo-submission-submitted")
        block = next(item for item in submission["stats"] if item["content_type"] == "stat")
        form = MultiDict([
            ("content_id", block["id"]),
            ("content_type", "stat"),
            (f"edited_text_{block['id']}", "The athlete won the race."),
            (f"entity_ids_{block['id']}", "entity-athlete-rast"),
            (f"entity_mention_{block['id']}_entity-athlete-rast", "Camille Rast"),
        ])
        with app.test_request_context("/"), patch(
            "services.sports_editorial.auth.current_user",
            return_value={"id": "demo-sub-editor", "full_name": "Nick L.", "role": "sub_editor"},
        ):
            updated = repository.update_review(submission["id"], form, "in_review")
        self.assertNotIn("entity-athlete-rast", updated["stats"][0]["entity_ids"])
        self.assertNotIn("entity-athlete-rast", updated["stats"][0]["entity_mentions"])

    def test_entity_editor_removes_stale_chip_so_entity_can_be_relinked(self):
        script = Path("static/js/sports-editorial-review.js").read_text(encoding="utf-8")
        self.assertIn("chip.remove();", script)
        self.assertIn("existingChip = null;", script)
        self.assertIn("unwrapMentionTags(editor);\n    validateMentionTags();", script)

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

    def test_fis_payload_links_all_supported_entity_types(self):
        submission = {
            "id": "sheet-1", "title": "Linked sheet", "sport": "alpine_skiing", "gender": "W",
            "fis_event_ids": [62716], "stats": [{"id": "stat-1", "sort_order": 0, "stat_text": "Linked fact", "entity_ids": ["a", "n", "e", "c"]}],
        }
        entities = {
            "a": {"entity_type": "athlete", "canonical_id": "516562"},
            "n": {"entity_type": "country", "canonical_id": "SUI"},
            "e": {"entity_type": "event", "canonical_id": "62716"},
            "c": {"entity_type": "competition", "canonical_id": "131458"},
        }
        links = build_fis_payload(submission, entities)["sections"][0]["items"][0]["links"]
        self.assertEqual(links, [
            {"type": "athlete", "id": "516562"}, {"type": "nation", "id": "SUI"},
            {"type": "event", "id": "62716"}, {"type": "competition", "id": "131458"},
        ])

    def test_fis_payload_generates_inline_marker_and_separate_note(self):
        submission = {
            "id": "sheet-1", "title": "Linked sheet", "sport": "alpine_skiing", "gender": "W",
            "fis_event_ids": [62716], "editor_notes": "Internal only", "fis_submission_notes": "V2 corrects a result.",
            "stats": [{"id": "stat-1", "sort_order": 0, "stat_text": "Camille Rast won. Camille Rast celebrated.", "entity_ids": ["a"], "entity_mentions": {"a": "Camille Rast"}}],
        }
        entities = {"a": {"entity_type": "athlete", "canonical_id": "516562", "name": "Camille Rast"}}
        payload = build_fis_payload(submission, entities)
        self.assertEqual(
            payload["sections"][0]["items"][0]["text"],
            "{{athlete:516562|Camille Rast}} won. Camille Rast celebrated.",
        )
        self.assertNotIn("notes", payload)
        self.assertNotIn("Internal only", json.dumps(payload))

    def test_fis_preflight_rejects_contract_limits(self):
        submission = {
            "id": "sheet-1", "title": "x" * 256, "sport": "alpine_skiing", "fis_event_ids": [62716],
            "stats": [{"id": "stat-1", "sort_order": 0, "stat_text": "x" * 5001, "entity_ids": [], "tags": [f"tag-{index}" for index in range(11)]}],
        }
        with self.assertRaises(FisPayloadValidationError) as context:
            build_fis_payload(submission, {})
        message = str(context.exception)
        self.assertIn("255", message)
        self.assertIn("5,000", message)
        self.assertIn("more than 10", message)

    def test_live_client_blocks_unknown_remote_schema(self):
        client = LiveFisClient("https://fis.invalid", "token", safe_event_ids=[62716], live_enabled=True)
        with patch.object(client, "get", return_value={"schemaVersion": 2, "version": 3}):
            with self.assertRaises(FisApiError) as context:
                client.publish("wc-al-w-test-2027", {"eventIds": [62716]})
        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("schema version 2", str(context.exception))

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
        self.assertEqual(repository.get_submission("demo-submission-approved")["status"], "draft")

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
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'contenteditable="true"', response.data)
        self.assertIn(b'aria-label="Statistic wording"', response.data)
        self.assertIn(b"View original researcher wording", response.data)
        self.assertIn(b"Save &amp; close", response.data)
        self.assertIn(b'target="_blank"', response.data)
        self.assertIn(b"data-accepted-count", response.data)
        self.assertIn(b'class="sew-content-list" data-review-list', response.data)
        self.assertIn(b'class="sew-card-header-actions"', response.data)

    def test_save_and_close_returns_to_stat_sheet_queue(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={
            "status": "submitted", "fis_event_ids": "55596", "save_action": "close",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/workspace/sports-editorial/queue"))

    def test_accepted_statistic_places_unlock_in_card_header(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-approved?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Accepted \xc2\xb7 locked</span><button class="sew-button sew-button--danger sew-button--small" type="button" data-toggle-accepted', response.data)
        self.assertNotIn(b'class="sew-review-actions"', response.data)

    def test_unaccepted_statistic_places_accept_and_lock_in_card_header(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Needs review</span><button class="sew-button sew-button--primary sew-button--small" type="button" data-toggle-accepted', response.data)

    def test_only_drag_handles_are_draggable_so_original_wording_is_selectable(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'data-review-block data-block-type="stat" data-accepted="0" draggable=', response.data)
        self.assertIn(b'class="sew-drag" title="Drag to reorder" draggable="true"', response.data)
        self.assertIn(b'class="sew-rendered-content"', response.data)

    def test_sub_editor_gets_explicit_review_actions_instead_of_status_dropdown(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current stage: In Sub Edit", response.data)
        self.assertIn(b'value="changes_requested">Request changes', response.data)
        self.assertIn(b'value="approved">Approve stat sheet', response.data)
        self.assertNotIn(b"<span>Workflow status</span><select", response.data)

    def test_request_changes_requires_feedback_and_reopens_researcher_editing(self):
        self.set_sub_editor()
        missing_feedback = self.client.post(
            "/workspace/sports-editorial/submissions/demo-submission-submitted",
            data={"status": "changes_requested", "fis_event_ids": "55596"},
            follow_redirects=True,
        )
        self.assertIn(b"Add instructions explaining what the researcher needs to change", missing_feedback.data)
        self.assertEqual(repository.get_submission("demo-submission-submitted")["status"], "in_review")

        feedback = "Please replace the final statistic and confirm its source."
        response = self.client.post(
            "/workspace/sports-editorial/submissions/demo-submission-submitted",
            data={"status": "changes_requested", "fis_event_ids": "55596", "editor_notes": feedback},
            follow_redirects=True,
        )
        self.assertIn(b"Changes requested", response.data)
        self.assertEqual(repository.get_submission("demo-submission-submitted")["status"], "changes_requested")
        self.assertEqual(repository.get_submission("demo-submission-submitted")["editor_notes"], feedback)
        self.set_role("researcher")
        researcher_view = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted")
        self.assertIn(feedback.encode(), researcher_view.data)
        self.assertIn(b"Continue research", researcher_view.data)

    def test_approved_sheet_offers_fis_json_without_publish_action(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-approved?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Approved and ready for JSON", response.data)
        self.assertIn(b"Review FIS JSON", response.data)
        self.assertIn(b"Return to sub-edit", response.data)
        self.assertNotIn(b"Simulate publish", response.data)

    def test_create_stat_sheet_action_is_on_sub_editor_queue(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue")
        self.assertIn(b"Your logo", response.data)
        self.assertIn(b">here</small>", response.data)
        self.assertNotIn(b"AMP Media Sports Editorial", response.data)
        self.assertIn(b"Create stat sheet", response.data)
        self.set_role("researcher")
        response = self.client.get("/workspace/sports-editorial/queue")
        self.assertNotIn(b"Create stat sheet", response.data)

    def test_queue_has_permanently_visible_filters_without_redundant_status_banner(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue?status=submitted&competition=FIS+World+Cup&sort=event_name:asc")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<section class="sew-queue-filter-panel sew-queue-filter-panel--always-open"', response.data)
        self.assertIn(b'data-filter-field="competition"', response.data)
        self.assertIn(b'data-filter-field="status"', response.data)
        self.assertIn(b'class="sew-card sew-table-card sew-queue-table-card"', response.data)
        self.assertIn(b'type="checkbox" name="status" value="submitted" checked', response.data)
        self.assertIn(b"Type to narrow", response.data)
        self.assertIn(b"Apply filters", response.data)
        self.assertIn(b"Reset filters", response.data)
        self.assertIn(b"<summary><span>Status</span><b>1 selected</b></summary>", response.data)
        self.assertIn(b"<summary><span>Competition</span><b>1 selected</b></summary>", response.data)
        self.assertIn(b'data-filter-field="season_code"', response.data)
        self.assertNotIn(b"Showing 1 of 3 stat sheets:", response.data)
        self.assertNotIn(b"Clear all filters", response.data)
        self.assertIn(b'name="sort" value="event_name:asc"', response.data)
        self.assertIn(b'aria-sort="ascending"', response.data)
        self.assertIn(b'aria-sort="none"', response.data)

    def test_queue_accepts_multiple_values_for_one_filter(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue?status=submitted&status=approved")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b">560001</td>", response.data)
        self.assertIn(b">560002</td>", response.data)
        self.assertIn(b">560003</td>", response.data)
        self.assertIn(b"<summary><span>Status</span><b>2 selected</b></summary>", response.data)
        self.assertIn(b'value="submitted" checked', response.data)
        self.assertIn(b'value="approved" checked', response.data)
        self.assertIn(b"status=submitted&amp;status=approved", response.data)

    def test_queue_uses_open_buttons_and_plain_selectable_rows(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<th>Open</th>", response.data)
        self.assertIn(b'class="sew-queue-row"', response.data)
        self.assertIn(b'class="sew-button sew-button--primary sew-button--small sew-open-sheet"', response.data)
        self.assertNotIn(b"data-row-href", response.data)
        self.assertNotIn(b"class=\"sew-cell-filter\"", response.data)
        self.assertIn(b'data-submission-id="demo-submission-kronplatz"', response.data)
        self.assertNotIn(b'aria-describedby="queue-interaction-help"', response.data)
        self.assertIn(b"Client Event ID", response.data)
        self.assertIn(b"Allocate researcher", response.data)
        self.assertIn(b"Allocate sub-editor", response.data)
        self.assertIn(b"Select all visible", response.data)

    def test_researcher_queue_keeps_filters_visible_without_selection_controls(self):
        response = self.client.get("/workspace/sports-editorial/queue")
        self.assertIn(b'sew-queue-filter-panel--always-open', response.data)
        self.assertIn(b'data-filter-field="season_code"', response.data)
        self.assertNotIn(b"Showing all 3 stat sheets", response.data)
        self.assertNotIn(b"Allocate researcher", response.data)
        self.assertIn(b'aria-sort="descending"', response.data)

    def test_queue_supports_cumulative_sorting(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue?sort=competition:asc,event_name:desc")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sorted by Competition ascending, then Event Name descending", response.data)
        self.assertIn(b"Clear sorting", response.data)
        self.assertIn(b'<b>1</b>', response.data)
        self.assertIn(b'<b>2</b>', response.data)

    def test_queue_toggle_exposes_enhanced_view_with_integrated_filters_and_checkbox_selection(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/queue/modern-preview")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enhanced stat sheet view", response.data)
        self.assertIn(b'aria-label="Filter by Competition"', response.data)
        self.assertIn(b'data-row-select', response.data)
        self.assertIn(b"Allocate researcher", response.data)
        self.assertIn(b'data-current-view="enhanced"', response.data)
        standard = self.client.get("/workspace/sports-editorial/queue?status=submitted")
        self.assertIn(b'data-current-view="standard"', standard.data)
        self.assertIn(b'href="/workspace/sports-editorial/queue/modern-preview?status=submitted"', standard.data)
        self.assertIn(b">Standard</a><a", standard.data)
        self.assertIn(b">Enhanced</a>", standard.data)

    def test_core_stat_sheet_data_is_open_collapsible_and_compact(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<details class="sew-card sew-core-data sew-core-summary" open>', response.data)
        self.assertIn(b"<strong>Core stat-sheet data</strong>", response.data)
        self.assertIn(b'class="sew-core-summary__body"', response.data)
        self.assertIn(b'<span>Title</span><input name="title"', response.data)
        self.assertNotIn(b'type="date" name="event_date" value="None"', response.data)

    def test_sub_editor_can_bulk_allocate_and_unallocate_researchers(self):
        self.set_sub_editor()
        selected = ["demo-submission-kronplatz", "demo-submission-submitted"]
        response = self.client.post("/workspace/sports-editorial/queue/bulk-assign", data={
            "submission_id": selected,
            "assignment_field": "researcher_user_id",
            "assignment_action": "allocate",
            "user_id": "demo-researcher-2",
        })
        self.assertEqual(response.status_code, 302)
        for submission_id in selected:
            self.assertEqual(repository.get_submission(submission_id)["researcher_user_id"], "demo-researcher-2")
            self.assertEqual(repository.get_submission(submission_id)["researcher_name"], "Andrew Hendry")

        response = self.client.post("/workspace/sports-editorial/queue/bulk-assign", data={
            "submission_id": selected,
            "assignment_field": "researcher_user_id",
            "assignment_action": "unallocate",
        })
        self.assertEqual(response.status_code, 302)
        for submission_id in selected:
            self.assertIsNone(repository.get_submission(submission_id)["researcher_user_id"])

    def test_researcher_cannot_bulk_allocate_stat_sheets(self):
        self.set_role("researcher")
        response = self.client.post("/workspace/sports-editorial/queue/bulk-assign", data={
            "submission_id": "demo-submission-kronplatz",
            "assignment_field": "sub_editor_user_id",
            "assignment_action": "unallocate",
        })
        self.assertEqual(response.status_code, 403)

    def test_approval_requires_every_block_to_be_accepted(self):
        self.set_sub_editor()
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={"status": "approved", "fis_event_ids": "55596"}, follow_redirects=True)
        self.assertIn(b"Accept and lock every statistic", response.data)
        self.assertEqual(repository.get_submission("demo-submission-submitted")["status"], "in_review")

    def test_sub_headings_do_not_require_explicit_acceptance(self):
        self.set_sub_editor()
        sheet = repository.get_submission("demo-submission-kronplatz")
        data = {"status": "approved", "fis_event_ids": "55596"}
        for block in sheet["stats"]:
            data.setdefault("content_id", []).append(block["id"])
            data.setdefault("content_type", []).append(block["content_type"])
            data[f"edited_text_{block['id']}"] = block.get("edited_text") or block["stat_text"]
            if block["content_type"] == "stat":
                data[f"accepted_{block['id']}"] = "1"
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-kronplatz", data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(repository.get_submission("demo-submission-kronplatz")["status"], "approved")

    def test_sub_editor_can_add_remove_and_reorder_blocks(self):
        self.set_sub_editor()
        sheet = repository.get_submission("demo-submission-submitted")
        original_id = sheet["stats"][0]["id"]
        new_heading_id = "11111111-1111-4111-8111-111111111111"
        new_stat_id = "22222222-2222-4222-8222-222222222222"
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={
            "status": "in_review", "fis_event_ids": "55596",
            "content_id": [new_heading_id, new_stat_id], "content_type": ["section", "stat"],
            f"edited_text_{new_heading_id}": "New heading", f"edited_text_{new_stat_id}": "New statistic",
            f"accepted_{new_stat_id}": "0",
        })
        self.assertEqual(response.status_code, 302)
        updated = repository.get_submission("demo-submission-submitted")
        self.assertEqual([block["id"] for block in updated["stats"]], [new_heading_id, new_stat_id])
        self.assertNotIn(original_id, [block["id"] for block in updated["stats"]])

    def test_editing_published_sheet_only_unlocks_changed_statistics(self):
        self.set_sub_editor()
        created = repository.create_submission({
            "title": "Published correction", "sport": "alpine_skiing", "competition": "World Cup", "event_name": "GS",
            "gender": "W", "location": "Kronplatz", "event_date": "2026-01-01", "fis_event_ids": [55596],
            "author_name": "Sub", "author_email": "", "content": [{"content_type": "stat", "content_html": "First"}, {"content_type": "stat", "content_html": "Second"}],
        }, "submitted")
        blocks = created["stats"]
        review = {"status": "approved", "fis_event_ids": "55596", "content_id": [b["id"] for b in blocks], "content_type": ["stat", "stat"]}
        for block in blocks:
            review[f"edited_text_{block['id']}"] = block["stat_text"]
            review[f"accepted_{block['id']}"] = "1"
        self.client.post(f"/workspace/sports-editorial/submissions/{created['id']}", data=review)
        repository.set_submission_status(created["id"], "exported")
        edit = self.client.post(f"/workspace/sports-editorial/submissions/{created['id']}/edit")
        self.assertEqual(edit.status_code, 302)
        self.assertEqual(repository.get_submission(created["id"])["status"], "draft")
        self.client.post(f"/workspace/sports-editorial/submissions/{created['id']}/research", data={
            "action": "submit", "content_id": [b["id"] for b in blocks], "content_type": ["stat", "stat"],
            "content_html": ["First corrected", "Second"], "event_date": "01-Jan-2026",
        })
        revised = repository.get_submission(created["id"])
        self.assertIsNone(revised["stats"][0]["accepted_at"])
        self.assertIsNotNone(revised["stats"][1]["accepted_at"])

    def test_publication_preview_is_visual_and_not_a_publish_action(self):
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/publication-preview")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sew-preview-page", response.data)
        self.assertNotIn(b"Working Notes", response.data)
        self.assertNotIn(b"All Stat Sheets", response.data)
        self.assertNotIn(b"Back to stat sheet", response.data)
        self.assertNotIn(b"/workspace/sports-editorial", response.data)
        self.assertNotIn(b"sew-publication-identity", response.data)
        self.assertNotIn(b"<dt>Race date</dt>", response.data)
        self.assertNotIn(b"<dt>AMP ID</dt>", response.data)
        self.assertNotIn(b"<dt>Status</dt>", response.data)

    def test_research_core_data_uses_single_clean_race_date_control(self):
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Only Race Date is editable", response.data)
        self.assertNotIn(b"Race Date <em>Editable</em>", response.data)
        self.assertIn(b'<span>Race Date</span><span class="sew-date-control">', response.data)

    def test_queue_open_routes_directly_to_the_role_appropriate_editor(self):
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        researcher_queue = self.client.get("/workspace/sports-editorial/queue")
        self.assertIn(
            b'href="/workspace/sports-editorial/submissions/demo-submission-kronplatz/research"',
            researcher_queue.data,
        )
        opened = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(repository.get_edit_lock("demo-submission-kronplatz")["owner_id"], "demo-user")

        self.set_sub_editor()
        sub_editor_queue = self.client.get("/workspace/sports-editorial/queue")
        self.assertIn(
            b'href="/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1"',
            sub_editor_queue.data,
        )

    def test_research_save_stays_in_editor_and_retains_lock(self):
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        submission = repository.get_submission("demo-submission-kronplatz")
        self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        original_lock = repository.get_edit_lock("demo-submission-kronplatz")
        response = self.client.post(
            "/workspace/sports-editorial/submissions/demo-submission-kronplatz/research",
            data={
                "action": "draft",
                "event_date": "27-Oct-2026",
                "content_id": [block["id"] for block in submission["stats"]],
                "content_type": [block["content_type"] for block in submission["stats"]],
                "content_html": [block["stat_text"] for block in submission["stats"]],
                "lock_token": original_lock["token"],
                "lock_version": original_lock["version"],
            },
        )
        retained_lock = repository.get_edit_lock("demo-submission-kronplatz")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/research"))
        self.assertEqual(retained_lock["token"], original_lock["token"])
        self.assertEqual(retained_lock["version"], original_lock["version"])

    def test_edit_lock_acquisition_is_atomic_and_owner_can_reopen(self):
        users = [
            {"id": "editor-a", "full_name": "Editor A"},
            {"id": "editor-b", "full_name": "Editor B"},
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda user: repository.acquire_edit_lock("demo-submission-submitted", user), users))
        owners = [lock["owner_id"] for _sheet, lock in results]
        self.assertEqual(len(set(owners)), 1)
        owner = next(user for user in users if user["id"] == owners[0])
        _sheet, reopened = repository.acquire_edit_lock("demo-submission-submitted", owner)
        self.assertEqual(reopened["token"], results[owners.index(owner["id"])][1]["token"])

    def test_edit_lock_expires_after_inactivity_and_heartbeat_renews(self):
        user = {"id": "editor-a", "full_name": "Editor A"}
        with patch.dict(os.environ, {"SPORTS_EDITORIAL_EDIT_LOCK_TIMEOUT_SECONDS": "60"}):
            _sheet, lock = repository.acquire_edit_lock("demo-submission-submitted", user)
            renewed = repository.heartbeat_edit_lock("demo-submission-submitted", user["id"], lock["token"])
            self.assertIsNotNone(renewed)
            item = next(row for row in repository._submissions if row["id"] == "demo-submission-submitted")
            item["lock_last_active_at"] = (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat()
            self.assertIsNone(repository.get_edit_lock("demo-submission-submitted"))
            _sheet, replacement = repository.acquire_edit_lock(
                "demo-submission-submitted", {"id": "editor-b", "full_name": "Editor B"}
            )
            self.assertEqual(replacement["owner_id"], "editor-b")
            self.assertNotEqual(replacement["token"], lock["token"])

    def test_edit_lock_form_uses_default_sixty_minute_timeout(self):
        self.set_sub_editor()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-lock-timeout="3600"', response.data)

    def test_researcher_can_reacquire_an_expired_lock_from_saved_sheet(self):
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        _sheet, original = repository.acquire_edit_lock(
            "demo-submission-kronplatz", {"id": "demo-user", "full_name": "Jamie Laurent"}
        )
        item = next(row for row in repository._submissions if row["id"] == "demo-submission-kronplatz")
        item["lock_last_active_at"] = (datetime.now(timezone.utc) - timedelta(seconds=3601)).isoformat()
        response = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        replacement = repository.get_edit_lock("demo-submission-kronplatz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replacement["owner_id"], "demo-user")
        self.assertNotEqual(replacement["token"], original["token"])

    def test_locked_sheet_is_read_only_and_force_unlock_is_supervisor_only(self):
        _sheet, displaced_lock = repository.acquire_edit_lock(
            "demo-submission-submitted", {"id": "other-editor", "full_name": "Other Editor"}
        )
        self.set_sub_editor()
        page = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted")
        self.assertIn(b"This sheet is locked by Other Editor", page.data)
        self.assertIn(b"read-only version", page.data)
        denied = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted/force-unlock")
        self.assertEqual(denied.status_code, 403)
        self.set_role("supervisor")
        allowed = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted/force-unlock")
        self.assertEqual(allowed.status_code, 302)
        supervisor_lock = repository.get_edit_lock("demo-submission-submitted")
        self.assertEqual(supervisor_lock["owner_id"], "demo-user")
        self.assertNotEqual(supervisor_lock["token"], displaced_lock["token"])
        self.assertGreater(supervisor_lock["version"], displaced_lock["version"])
        self.assertFalse(repository.verify_edit_lock(
            "demo-submission-submitted", "other-editor", displaced_lock["token"], displaced_lock["version"]
        ))

    def test_force_takeover_migration_is_atomic_and_service_role_only(self):
        migration = Path("supabase/sports_editorial_edit_locks.sql").read_text(encoding="utf-8")
        self.assertIn("sports_editorial_force_takeover_edit_lock", migration)
        self.assertIn("lock_token = gen_random_uuid()", migration)
        self.assertIn("lock_version = lock_version + 1", migration)
        self.assertIn(
            "revoke all on function public.sports_editorial_force_takeover_edit_lock",
            migration,
        )
        self.assertIn(
            "grant execute on function public.sports_editorial_force_takeover_edit_lock(uuid,uuid,uuid,text) to service_role",
            migration,
        )

    def test_entity_linking_requires_deliberate_selected_text_action(self):
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        page = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        self.assertIn(b'data-link-entity', page.data)
        self.assertIn(b'aria-label="Add entity link"', page.data)
        script = Path("static/js/sports-editorial-review.js").read_text(encoding="utf-8")
        self.assertIn('editor.addEventListener("contextmenu"', script)
        self.assertIn("selectedMentionContext", script)
        self.assertNotIn("currentQuery", script)
        self.assertNotIn('editor.addEventListener("input", () => {\n      scheduleSearch', script)

    def test_stale_lock_token_cannot_save_after_takeover(self):
        self.set_sub_editor()
        page = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(page.status_code, 200)
        old = repository.get_edit_lock("demo-submission-submitted")
        repository.release_edit_lock("demo-submission-submitted", force=True)
        repository.acquire_edit_lock("demo-submission-submitted", {"id": "supervisor-user", "full_name": "Supervisor"})
        response = self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted", data={
            "lock_token": old["token"], "lock_version": old["version"], "status": "submitted",
        })
        self.assertEqual(response.status_code, 409)

    def test_researcher_queue_has_counts_selection_and_publication_preview(self):
        response = self.client.get("/workspace/sports-editorial/queue")
        self.assertIn(b'<span data-selected-count>0</span> of 3 sheets', response.data)
        self.assertIn(b"data-row-select", response.data)
        repository.set_submission_status("demo-submission-kronplatz", "draft")
        preview_link = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/research")
        self.assertIn(b"Publication preview", preview_link.data)
        preview = self.client.get("/workspace/sports-editorial/submissions/demo-submission-kronplatz/publication-preview")
        self.assertEqual(preview.status_code, 200)

    def test_entity_search_paginates_and_reports_more(self):
        for index in range(15):
            repository.add_entity({"entity_type": "athlete", "name": f"Laura Test {index:02d}", "canonical_id": str(700000 + index)})
        first = self.client.get("/workspace/sports-editorial/entities/search?q=Laura&type=athlete").get_json()
        self.assertEqual(len(first["results"]), 10)
        self.assertTrue(first["has_more"])
        second = self.client.get(f"/workspace/sports-editorial/entities/search?q=Laura&type=athlete&offset={first['next_offset']}").get_json()
        self.assertEqual(len(second["results"]), 5)
        self.assertFalse(second["has_more"])

    def test_entity_link_rendering_is_safe_and_degrades_without_url(self):
        block = {"entity_ids": ["safe", "plain"], "entity_mentions": {"safe": "Laura", "plain": "Pirovano"}}
        entities = {
            "safe": {"canonical_url": "https://example.test/athletes/1"},
            "plain": {"canonical_url": "javascript:alert(1)"},
        }
        rendered = render_entity_links("<strong>Laura Pirovano</strong><script>bad()</script>", block, entities)
        self.assertIn('href="https://example.test/athletes/1"', rendered)
        self.assertIn("Pirovano", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("<script>", rendered)

    def test_country_publication_links_exact_saved_wording_only_with_valid_url(self):
        entity = {
            "country": {
                "entity_type": "country", "canonical_id": "SUI",
                "canonical_url": "https://www.fis-ski.com/example-country-source",
            },
        }
        for mention in ("SUI", "Switzerland"):
            with self.subTest(mention=mention):
                block = {"entity_ids": ["country"], "entity_mentions": {"country": mention}}
                rendered = render_entity_links(f"Camille Rast represents {mention}.", block, entity)
                self.assertIn(f'>{mention}</a>', rendered)
                self.assertIn('href="https://www.fis-ski.com/example-country-source"', rendered)

        entity["country"]["canonical_url"] = ""
        block = {"entity_ids": ["country"], "entity_mentions": {"country": "Switzerland"}}
        rendered = render_entity_links("Camille Rast represents Switzerland.", block, entity)
        self.assertIn("Switzerland", rendered)
        self.assertNotIn("<a ", rendered)

    def test_review_entity_validation_accepts_three_letter_country_id(self):
        form = MultiDict([
            ("content_id", "stat-1"),
            ("entity_ids_stat-1", "entity-country-ch"),
        ])
        self.assertEqual(
            sports_editorial_views._invalid_review_entity_links(form, {"stats": [{"id": "stat-1"}]}),
            [],
        )

    def test_entity_linking_decorates_only_first_exact_occurrence(self):
        block = {"entity_ids": ["rast"], "entity_mentions": {"rast": "Camille Rast"}}
        entities = {"rast": {"canonical_url": "https://example.test/athletes/rast"}}
        rendered = render_entity_links(
            "Camille Rast won. Rast led early. <strong>Camille Rast</strong> won again.",
            block,
            entities,
        )
        self.assertEqual(rendered.count('data-entity-ref="rast"'), 1)
        self.assertIn("<strong>Camille Rast</strong> won again", rendered)
        self.assertIn("Rast led early", rendered)

    def test_read_only_open_does_not_lock_and_edit_open_changes_stage(self):
        self.set_sub_editor()
        read_only = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted")
        self.assertEqual(read_only.status_code, 200)
        self.assertIsNone(repository.get_edit_lock("demo-submission-submitted"))
        self.assertEqual(repository.get_submission("demo-submission-submitted")["status"], "submitted")
        editing = self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        self.assertEqual(editing.status_code, 200)
        self.assertEqual(repository.get_edit_lock("demo-submission-submitted")["owner_id"], "demo-user")
        self.assertEqual(repository.get_submission("demo-submission-submitted")["status"], "in_review")

    def test_owned_release_endpoint_closes_lock_without_timeout(self):
        self.set_sub_editor()
        self.client.get("/workspace/sports-editorial/submissions/demo-submission-submitted?edit=1")
        lock = repository.get_edit_lock("demo-submission-submitted")
        released = self.client.post(
            "/workspace/sports-editorial/submissions/demo-submission-submitted/edit-lock/release",
            data={"lock_token": lock["token"]},
        )
        self.assertEqual(released.status_code, 204)
        self.assertIsNone(repository.get_edit_lock("demo-submission-submitted"))

    def test_publish_and_force_unlock_are_audited(self):
        self.set_sub_editor()
        self.client.post("/workspace/sports-editorial/submissions/demo-submission-approved/fis-publish")
        self.assertEqual(repository.get_submission("demo-submission-approved")["status"], "exported")
        self.assertEqual(repository.list_audit_events("demo-submission-approved")[-1]["action"], "published")
        repository.acquire_edit_lock("demo-submission-submitted", {"id": "other-editor", "full_name": "Other Editor"})
        self.set_role("supervisor")
        self.client.post("/workspace/sports-editorial/submissions/demo-submission-submitted/force-unlock")
        audit = repository.list_audit_events("demo-submission-submitted")[-1]
        self.assertEqual(audit["action"], "force_unlock")
        self.assertEqual(audit["details"]["previous_owner_name"], "Other Editor")

    def test_editorial_supervisor_can_provision_supervisor_user(self):
        supervisor = {"id": "supervisor-id", "workspace_id": "workspace-id", "role": "supervisor", "workspace_role": "member"}
        with patch("services.sports_editorial.views.auth_configuration", return_value={"mode": "workspace"}), \
             patch("services.sports_editorial.views.current_user", return_value=supervisor), \
             patch("services.sports_editorial.views.require_editorial_user_admin", return_value=supervisor), \
             patch("services.sports_editorial.views.provision_workspace_user") as provision, \
             patch("services.sports_editorial.views.list_workspace_users", return_value=[]):
            response = self.client.post("/workspace/sports-editorial/users", data={
                "email": "new-supervisor@example.test", "full_name": "New Supervisor",
                "temporary_password": "temporary-passphrase", "editorial_role": "supervisor",
            })
        self.assertEqual(response.status_code, 302)
        provision.assert_called_once_with(
            "workspace-id", "new-supervisor@example.test", "New Supervisor",
            "temporary-passphrase", "supervisor",
        )

    def test_fis_calendar_parser_deduplicates_event_links(self):
        html = '''
        <a href="/DB/general/event-details.html?eventid=62716&amp;seasoncode=2027&amp;sectorcode=AL">28-31 Jul</a>
        <a href="/DB/general/event-details.html?eventid=62716&amp;seasoncode=2027&amp;sectorcode=AL">Cerro Castor, Ushuaia FIS 4xGS 4xSL</a>
        <a href="/DB/general/event-details.html?eventid=62984&amp;seasoncode=2027&amp;sectorcode=AL">Sestriere World Cup GS</a>
        '''
        events = parse_calendar_events(html, "https://www.fis-ski.com/DB/general/calendar-results.html", 2027)
        self.assertEqual([item["canonical_id"] for item in events], ["62716", "62984"])
        self.assertEqual(events[0]["name"], "Cerro Castor, Ushuaia FIS 4xGS 4xSL")
        self.assertEqual(events[0]["metadata"]["category_code"], "WC")

    def test_fis_athlete_csv_parser_uses_fis_code(self):
        content = (
            "Competitorid\tSectorcode\tFiscode\tLastname\tFirstname\tGender\tBirthdate\tNationcode\tStatus\r\n"
            "12345\tAL\t512345\tRAST\tCamille\tW\t1999-07-09\tSUI\tO\r\n"
            "23456\tAL\t422222\tTEAM\t\tA\t\tNOR\tE\r\n"
        ).encode()
        athletes = parse_athlete_csv(content, "https://www.fis-ski.com/example.zip", 2027, "4th list")
        self.assertEqual(len(athletes), 1)
        self.assertEqual(athletes[0]["canonical_id"], "512345")
        self.assertEqual(athletes[0]["name"], "Camille Rast")
        self.assertEqual(athletes[0]["country_code"], "SUI")
        self.assertEqual(athletes[0]["metadata"]["competitor_id"], "12345")

    def test_fis_countries_are_derived_from_official_athlete_codes(self):
        countries = countries_from_athletes([{"country_code": "SUI"}, {"country_code": "USA"}, {"country_code": "SUI"}])
        self.assertEqual([(item["canonical_id"], item["name"]) for item in countries], [("SUI", "Switzerland"), ("USA", "United States")])
        self.assertTrue(all(item["canonical_url"] == "" for item in countries))

    def test_fis_competition_parser_retains_race_id_and_codex(self):
        html = '''<a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=AL&amp;raceid=131458"><div data-date="2026-07-31">31 Jul</div></a>
        <a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=AL&amp;raceid=131458">0251</a>
        <a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=AL&amp;raceid=131458"><div>Giant Slalom</div></a>
        <a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=AL&amp;raceid=131458"><div>M</div></a>'''
        items = parse_event_competitions(html, {"canonical_id": "62716", "name": "Cerro Castor", "country_code": "ARG"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["canonical_id"], "131458")
        self.assertEqual(items[0]["metadata"]["codex"], "0251")
        self.assertIn("Giant Slalom", items[0]["name"])

    def test_competition_parser_carries_event_season_for_result_imports(self):
        html = '''<a href="https://www.fis-ski.com/DB/general/results.html?raceid=131458"><div data-date="2026-07-31">31 Jul</div><div>Giant Slalom</div><div>W</div></a>'''
        items = parse_event_competitions(html, {"canonical_id": "62716", "name": "Cerro Castor", "metadata": {"season_code": 2027, "category_code": "WC"}})
        self.assertEqual(items[0]["metadata"]["season_code"], 2027)
        self.assertEqual(items[0]["metadata"]["category_code"], "WC")

    def test_historical_fis_result_layout_reads_six_column_athlete_name(self):
        html = '''
        <h1>Soelden (AUT)</h1>
        <option selected>28.10.2023 - Women's Giant Slalom | WC</option>
        <div data-formatted-date="October 28, 2023"></div>
        <a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=125871">
          <div class="g-lg-1 pr-1 bold justify-right">1</div>
          <div class="g-lg-1 gray justify-center">1</div>
          <div class="pr-1 g-lg-2 gray justify-right">516138</div>
          <div class="g-lg-6 bold justify-left">GUT-BEHRAMI Lara</div>
          <div class="g-lg-1 hidden-sm-down justify-left">1991</div>
          <span class="country__name-short">SUI</span>
          <div class="g-lg-2 blue bold justify-right">2:18.94</div>
        </a>'''
        rows = parse_fis_results(html, {"canonical_id": "118331", "metadata": {"season_code": 2024}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["athlete"], "GUT-BEHRAMI Lara")
        self.assertEqual(rows[0]["fis_code"], "516138")
        self.assertEqual(rows[0]["place"], 1)

    def test_inaugural_world_cup_layout_reads_legacy_identifier(self):
        html = '''
        <h1>Adelboden (SUI)</h1>
        <option selected>09.01.1967 - Men's Giant Slalom | WC</option>
        <a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=30378">
          <div class="g-lg-1 pr-1 bold justify-right">1</div>
          <div class="pr-1 g-lg-2 gray justify-right">-10427</div>
          <div class="g-lg-15 bold justify-left">KILLY Jean-Claude</div>
          <div class="g-lg-1 hidden-sm-down justify-left">1943</div>
          <span class="country__name-short">FRA</span>
          <div class="g-lg-2 blue bold justify-right">3:30.71</div>
        </a>'''
        rows = parse_fis_results(html, {"canonical_id": "8193", "metadata": {"season_code": 1967, "date": "1967-01-09"}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fis_code"], "-10427")
        self.assertEqual(rows[0]["athlete"], "KILLY Jean-Claude")

    def test_early_2000s_layout_reads_twelve_column_athlete_name(self):
        html = '''
        <h1>Lake Louise (CAN)</h1>
        <option selected>01.12.2002 - Men's Super G | WC</option>
        <a class="table-row" href="https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=14972">
          <div class="g-lg-1 pr-1 bold justify-right">1</div>
          <div class="pr-1 g-lg-2 gray justify-right">50024</div>
          <div class="g-lg-12 bold justify-left">EBERHARTER Stephan</div>
          <div class="g-lg-1 hidden-sm-down justify-left">1969</div>
          <span class="country__name-short">AUT</span>
          <div class="g-lg-2 blue bold justify-right">1:23.39</div>
        </a>'''
        rows = parse_fis_results(html, {"canonical_id": "16860", "metadata": {"season_code": 2003, "date": "2002-12-01"}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["athlete"], "EBERHARTER Stephan")

    def test_combined_entity_refresh_is_admin_only_in_workspace_mode(self):
        with patch("services.sports_editorial.views.auth_configuration", return_value={"mode": "workspace"}), patch("services.sports_editorial.views.current_user", return_value=None):
            response = self.client.post("/workspace/sports-editorial/entities/refresh/events", data={"season_code": "2027"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
