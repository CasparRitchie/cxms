import unittest

from app import app


class FaceFiltersPageTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_page_is_public_and_loads_local_assets(self):
        response = self.client.get("/face-filters")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Face Filters", response.data)
        self.assertIn(b"No account, no ads, no uploads", response.data)
        self.assertIn(b"data-start-camera", response.data)
        self.assertIn(b"data-record", response.data)
        self.assertIn(b'data-filter="big-eyes"', response.data)
        self.assertIn(b'data-filter="mega-mouth"', response.data)
        self.assertIn(b'data-filter="party-hat"', response.data)
        css_response = self.client.get("/static/css/face-filters.css")
        js_response = self.client.get("/static/js/face-filters.js")
        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(js_response.status_code, 200)
        css_response.close()
        js_response.close()

    def test_trailing_slash_route_is_supported(self):
        self.assertEqual(self.client.get("/face-filters/").status_code, 200)

    def test_client_side_privacy_and_recording_contract(self):
        response = self.client.get("/static/js/face-filters.js")
        script = response.data
        self.assertIn(b"FaceLandmarker.createFromOptions", script)
        self.assertIn(b"function drawMegaMouth", script)
        self.assertIn(b"detectForVideo", script)
        self.assertIn(b"navigator.mediaDevices.getUserMedia", script)
        self.assertIn(b"ui.canvas.captureStream", script)
        self.assertIn(b"new MediaRecorder", script)
        self.assertIn(b"MediaRecorder.isTypeSupported", script)
        self.assertIn(b"URL.createObjectURL", script)
        self.assertNotIn(b"fetch(", script)
        self.assertNotIn(b"XMLHttpRequest", script)
        response.close()


if __name__ == "__main__":
    unittest.main()
