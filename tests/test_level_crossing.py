import json
import unittest
from unittest.mock import patch

from app import app
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
        css_response = self.client.get("/static/css/level-crossing.css")
        js_response = self.client.get("/static/js/level-crossing.js")
        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(js_response.status_code, 200)
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


if __name__ == "__main__":
    unittest.main()
