import json
import os
import unittest
from unittest.mock import patch

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
from services.sports_editorial.repository import repository
from services.sports_editorial.stat_insights import build_editorial_discoveries, build_perspective_insights, build_stat_insights, demo_result_rows, group_editorial_discoveries
from services.sports_editorial.validation import validate_status_transition, validate_submission


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
            "/", "/games", "/circuit-training", "/gcse/history", "/football", "/data-explorer",
            "/sports-editorial", "/workspace/sports-editorial", "/workspace/sports-editorial/", "/workspace/sports-editorial/submit",
            "/workspace/sports-editorial/queue", "/workspace/sports-editorial/stat-insights",
        ]
        for path in paths:
            with self.subTest(path=path):
                expected = 403 if path == "/workspace/sports-editorial/submit" else 200
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
            "title": "Unassigned researcher test", "event_name": "Slalom", "gender": "W",
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
            "title": "Assigned sheet", "event_name": "Downhill", "gender": "M", "event_date": "2026-10-12",
            "fis_event_ids": "55596", "researcher_user_id": "demo-user", "sub_editor_user_id": "demo-sub-editor",
            "content_type": "", "content_html": "", "action": "draft",
        })
        submission_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.set_role("researcher")
        saved = self.client.post(f"/workspace/sports-editorial/submissions/{submission_id}/research", data={
            "event_date": "2026-10-13", "content_type": ["section", "stat"],
            "content_html": ["Race scenarios", "A researched statistic."],
            "working_notes": "Source: internal workbook", "unused_stats": "Reserve statistic", "action": "submit",
        })
        self.assertEqual(saved.status_code, 302)
        sheet = repository.get_submission(submission_id)
        self.assertEqual(sheet["status"], "submitted")
        self.assertEqual(sheet["event_date"], "2026-10-13")
        self.assertEqual([block["content_type"] for block in sheet["stats"]], ["section", "stat"])
        self.assertEqual(self.client.get(f"/workspace/sports-editorial/submissions/{submission_id}/research").status_code, 403)
        exported = build_pilot_export(sheet, {})
        self.assertNotIn("working_notes", json.dumps(exported))
        self.assertNotIn("unused_stats", json.dumps(exported))

    def test_supervisor_has_editor_creation_access(self):
        self.set_role("supervisor")
        self.assertEqual(self.client.get("/workspace/sports-editorial/submit").status_code, 200)

    def test_create_review_approve_and_download_workflow(self):
        self.set_sub_editor()
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
        self.assertEqual(payload["results"][0]["canonical_id"], "516562")

        invalid = self.client.get("/workspace/sports-editorial/entities/search?q=cam&type=invalid")
        self.assertEqual(invalid.status_code, 400)

        country = self.client.get("/workspace/sports-editorial/entities/search?q=SUI&type=country").get_json()
        self.assertEqual(country["results"][0]["name"], "Switzerland")

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
            "stats": [{"id": "stat-1", "sort_order": 0, "stat_text": "Camille Rast won.", "entity_ids": ["a"], "entity_mentions": {"a": "Camille Rast"}}],
        }
        entities = {"a": {"entity_type": "athlete", "canonical_id": "516562", "name": "Camille Rast"}}
        payload = build_fis_payload(submission, entities)
        self.assertEqual(payload["sections"][0]["items"][0]["text"], "{{athlete:516562|Camille Rast}} won.")
        self.assertEqual(payload["notes"], "V2 corrects a result.")
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

    def test_combined_entity_refresh_is_admin_only_in_workspace_mode(self):
        with patch("services.sports_editorial.views.auth_configuration", return_value={"mode": "workspace"}), patch("services.sports_editorial.views.current_user", return_value=None):
            response = self.client.post("/workspace/sports-editorial/entities/refresh/events", data={"season_code": "2027"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
