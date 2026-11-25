import os
import unittest
from unittest.mock import patch
from app import app


class SammyTVTests(unittest.TestCase):
    def setUp(self):
        self.mode = patch.dict(os.environ, {'SAMMYTV_MODE': 'preview'})
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.client = app.test_client()

    def test_routes_are_isolated_previews(self):
        for path in ('', '/', '/search?q=trains', '/channels', '/channel/rail', '/favourites', '/history', '/requests', '/admin', '/watch/coast'):
            with self.subTest(path=path):
                response = self.client.get('/sammytv' + path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Illustrative videos', response.data)
                self.assertIn("frame-src 'none'", response.headers['Content-Security-Policy'])
                self.assertNotIn(b'<iframe', response.data)

    def test_unknown_catalogue_ids_are_rejected(self):
        for path in ('/watch/unknown', '/channel/unknown'):
            self.assertEqual(self.client.get('/sammytv' + path).status_code, 404)

    def test_admin_has_no_mutations(self):
        self.assertEqual(self.client.post('/sammytv/admin').status_code, 405)
        self.assertIn(b'No administration actions', self.client.get('/sammytv/admin').data)

    def test_search_input_is_escaped(self):
        response = self.client.get('/sammytv/search', query_string={'q': '<script>alert(1)</script>'})
        self.assertNotIn(b'<script>alert(1)</script>', response.data)

    def test_preview_never_exposes_a_real_catalogue_or_enables_youtube(self):
        with patch.dict(os.environ, {'SAMMYTV_YOUTUBE_PLAYBACK_ENABLED': '1'}):
            response = self.client.get('/sammytv/watch/coast')
            self.assertIn("frame-src 'none'", response.headers['Content-Security-Policy'])
            self.assertNotIn(b'Load YouTube player', response.data)
            self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 503)

    def test_unknown_mode_fails_closed(self):
        with patch.dict(os.environ, {'SAMMYTV_MODE': 'mistyped-catalogue'}):
            response = self.client.get('/sammytv')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b'Along the coast', response.data)


if __name__ == '__main__':
    unittest.main()
