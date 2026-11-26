import os
import unittest
from unittest.mock import patch
from app import app
from test_sammytv_catalogue import SECRET, FAMILY, MEMBER, PROFILE, FakeRepository

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, SAMMYTV_MODE='catalogue', SAMMYTV_SESSION_SECRET=SECRET,
                              SAMMYTV_PARENT_EMAILS='parent@example.test')
        self.env.start()
        self.repo = FakeRepository()
        self.adapter = patch('services.sammytv.views.CatalogueRepository', return_value=self.repo)
        self.adapter.start()
        self.client = app.test_client()

    def tearDown(self):
        self.adapter.stop()
        self.env.stop()

    def token(self, path):
        response = self.client.get(path, base_url='https://localhost')
        self.assertEqual(response.status_code, 200)
        return self.client.get_cookie('sammytv_csrf', path='/sammytv').value

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/sammytv/signin').status_code, 400)
        self.assertEqual(self.client.post('/sammytv/pair').status_code, 400)

    def test_unlisted_unknown_parent_cannot_provision_a_family(self):
        token = self.token('/sammytv/signin')
        with patch.object(self.repo,'verify_parent',create=True,return_value=MEMBER), \
             patch.object(self.repo,'existing_parent',create=True,return_value=None), \
             patch.object(self.repo,'provision_parent',create=True) as provision:
            response = self.client.post('/sammytv/signin', base_url='https://localhost', data={
                'csrf_token': token, 'email': 'other@example.test', 'password': 'secret'})
            provision.assert_not_called()
        self.assertEqual(response.status_code, 401)

    def test_verified_parent_issues_private_cookie(self):
        token = self.token('/sammytv/signin')
        record = dict(member_id=MEMBER, family_id=FAMILY, profile_id=PROFILE, session_version=1)
        with patch.object(self.repo, 'verify_parent', create=True, return_value=MEMBER), \
             patch.object(self.repo, 'existing_parent', create=True, return_value=None), \
             patch.object(self.repo, 'provision_parent', create=True, return_value=record):
            response = self.client.post('/sammytv/signin', base_url='https://localhost', data={
                'csrf_token': token, 'email': 'parent@example.test', 'password': 'secret'})
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.getlist('Set-Cookie')[0]
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/sammytv'):
            self.assertIn(flag, cookie)

    def test_invalid_pairing_denied(self):
        token = self.token('/sammytv/pair')
        with patch.object(self.repo, 'redeem_pairing', create=True, return_value=None):
            response = self.client.post('/sammytv/pair', base_url='https://localhost', data={
                'csrf_token': token, 'code': 'a'*32})
        self.assertEqual(response.status_code, 401)
