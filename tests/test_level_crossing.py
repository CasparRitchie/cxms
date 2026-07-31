import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import app
from services.level_crossing.observations import (
    LevelCrossingObservationStore,
    ObservationRateLimiter,
    ObservationValidationError,
)
from services.level_crossing.td_feed import TrainDescriberFeed


class LevelCrossingPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_level_crossing_page_is_public_and_loads_assets(self):
        response = self.client.get("/level-crossing")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Chichester Crossing Monitor", response.data)
        self.assertIn(b"Whyke Road", response.data)
        self.assertIn(b"Simulation mode", response.data)
        self.assertIn(b"Route-planning prediction only", response.data)
        self.assertIn(b"Recent observations on this device", response.data)
        self.assertIn(b"Selected level crossings", response.data)
        self.assertIn(b"Start watch session", response.data)
        self.assertIn(b"Chichester live route helper", response.data)
        css_response = self.client.get("/static/css/level-crossing.css")
        js_response = self.client.get("/static/js/level-crossing.js")
        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(js_response.status_code, 200)
        self.assertIn(b"crossing-app-bar", css_response.data)
        self.assertIn(b"crossing-selection-chip-state", js_response.data)
        css_response.close()
        js_response.close()

    def test_trailing_slash_route_is_supported(self):
        self.assertEqual(self.client.get("/level-crossing/").status_code, 200)

    @patch("app.td_feed.start", return_value=False)
    @patch("app.td_feed.snapshot")
    def test_td_status_endpoint_is_public_and_safe(self, snapshot, _start):
        snapshot.return_value = {
            "configured": False,
            "status": "not_configured",
            "area": "CH",
            "messageCount": 0,
            "recentEvents": [],
        }

        response = self.client.get("/api/level-crossing/td-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "not_configured")
        self.assertNotIn(b"password", response.data.lower())

    @patch("app.observation_rate_limiter.allow", return_value=True)
    @patch("app.observation_store.save")
    @patch("app.td_feed.snapshot", return_value={"area": "CH", "recentEvents": []})
    @patch("app.td_feed.start", return_value=True)
    def test_observation_endpoint_stores_td_context(self, _start, _snapshot, save, _allow):
        save.return_value = {"id": "obs-12345678"}
        payload = {
            "id": "obs-12345678",
            "crossingId": "whyke-road",
            "state": "OPEN",
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "eventKind": "quick",
        }

        response = self.client.post("/api/level-crossing/observations", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"saved": True, "id": "obs-12345678"})
        save.assert_called_once_with(payload, {"area": "CH", "recentEvents": []})

    @patch("app.observation_rate_limiter.allow", return_value=False)
    def test_observation_endpoint_is_rate_limited(self, _allow):
        response = self.client.post("/api/level-crossing/observations", json={})

        self.assertEqual(response.status_code, 429)


class TrainDescriberFeedTests(unittest.TestCase):
    def setUp(self):
        self.feed = TrainDescriberFeed(
            environ={
                "NETWORK_RAIL_USERNAME": "test@example.com",
                "NETWORK_RAIL_PASSWORD": "not-returned-by-status",
                "NETWORK_RAIL_TD_AREA": "CH",
            }
        )

    def test_filters_to_chichester_and_tracks_berth_steps(self):
        payload = [
            {"CA_MSG": {"msg_type": "CA", "area_id": "CH", "from": "0101", "to": "0102", "descr": "1A23", "time": "123456"}},
            {"body": {"msg_type": "CA", "area_id": "CW", "from": "9999", "to": "9998", "descr": "9Z99", "time": "123457"}},
        ]

        self.assertEqual(self.feed.ingest(json.dumps(payload)), 1)
        status = self.feed.snapshot()
        self.assertEqual(status["frameCount"], 1)
        self.assertEqual(status["nationalMessageCount"], 2)
        self.assertEqual(status["messageCount"], 1)
        self.assertEqual(status["activeBerths"], {"0102": "1A23"})
        self.assertEqual(status["recentEvents"][0]["from"], "0101")
        self.assertNotIn("not-returned-by-status", str(status))

    def test_interpose_and_cancel_update_current_berths(self):
        self.feed.ingest({"body": {"msg_type": "CC", "area_id": "CH", "to": "0201", "descr": "2B45"}})
        self.feed.ingest({"body": {"msg_type": "CB", "area_id": "CH", "from": "0201"}})

        self.assertEqual(self.feed.snapshot()["activeBerths"], {})

    def test_connection_errors_redact_credentials(self):
        self.feed._set_error(RuntimeError("test@example.com not-returned-by-status"))

        error = self.feed.snapshot()["lastError"]
        self.assertNotIn("test@example.com", error)
        self.assertNotIn("not-returned-by-status", error)


class FakeSupabaseClient:
    configured = True

    def __init__(self):
        self.calls = []

    def request(self, table, method="GET", query=None, payload=None, prefer=None):
        self.calls.append((table, method, payload, prefer))
        return [payload]


class LevelCrossingObservationTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSupabaseClient()
        self.store = LevelCrossingObservationStore(client=self.client)
        self.payload = {
            "id": "obs-12345678",
            "crossingId": "whyke-road",
            "state": "TRAIN_PASSED",
            "eventKind": "watch",
            "sessionId": "session-12345678",
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "note": "First train",
            "prediction": {"state": "LIKELY_CLOSED", "demoTrainCount": 3},
        }

    def test_builds_anonymous_row_with_location_and_td_snapshot(self):
        saved = self.store.save(
            self.payload,
            {
                "area": "CH",
                "status": "connected",
                "lastMessageAt": "2026-07-31T15:25:01+00:00",
                "messageCount": 44,
                "recentEvents": [{"type": "CA", "from": "0101", "to": "0102"}],
                "activeBerths": {"0102": "1A23"},
                "lastError": "must not be stored",
            },
        )

        self.assertEqual(saved["crossing_name"], "Whyke Road")
        self.assertEqual(saved["what3words"], "awake.mason.melon")
        self.assertEqual(saved["td_snapshot"]["activeBerths"], {"0102": "1A23"})
        self.assertNotIn("lastError", saved["td_snapshot"])
        self.assertNotIn("ip", str(saved).lower())
        self.assertEqual(self.client.calls[0][0], "level_crossing_observations")
        self.assertIn("merge-duplicates", self.client.calls[0][3])

    def test_rejects_unknown_crossing_and_old_timestamp(self):
        self.payload["crossingId"] = "made-up-crossing"
        with self.assertRaises(ObservationValidationError):
            self.store.build_row(self.payload, {})

        self.payload["crossingId"] = "whyke-road"
        self.payload["observedAt"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        with self.assertRaises(ObservationValidationError):
            self.store.build_row(self.payload, {})

    def test_rate_limiter_allows_burst_then_blocks(self):
        limiter = ObservationRateLimiter(limit=2, window_seconds=60)
        now = datetime.now(timezone.utc)

        self.assertTrue(limiter.allow("device", now))
        self.assertTrue(limiter.allow("device", now))
        self.assertFalse(limiter.allow("device", now))
        self.assertTrue(limiter.allow("device", now + timedelta(seconds=61)))


if __name__ == "__main__":
    unittest.main()
