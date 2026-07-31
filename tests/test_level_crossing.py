import unittest

from app import app


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
        css_response = self.client.get("/static/css/level-crossing.css")
        js_response = self.client.get("/static/js/level-crossing.js")
        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(js_response.status_code, 200)
        css_response.close()
        js_response.close()

    def test_trailing_slash_route_is_supported(self):
        self.assertEqual(self.client.get("/level-crossing/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
