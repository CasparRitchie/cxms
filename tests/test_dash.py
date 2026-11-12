import unittest

from app import app


class DashPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_dash_home_is_available_with_or_without_trailing_slash(self):
        for path in ("/dash", "/dash/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Better work starts", response.data)

    def test_dash_home_contains_preliminary_product_structure(self):
        response = self.client.get("/dash")
        self.assertIn(b"My improvements", response.data)
        self.assertIn(b"Team view", response.data)
        self.assertIn(b"Improvement portfolio", response.data)
        self.assertIn(b"No live employee or organisation data", response.data)
        self.assertIn(b"LBGUPS stages plus Exit", response.data)

    def test_existing_home_page_is_unchanged(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Dash is an early concept", response.data)


if __name__ == "__main__":
    unittest.main()
