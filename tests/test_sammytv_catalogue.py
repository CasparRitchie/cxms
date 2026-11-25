"""Security and rendering tests. Database RPC integration is a separate staging check."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import jwt

from app import app
from services.sammytv.auth import AUDIENCE, COOKIE_NAME, ISSUER
from services.sammytv.catalogue import is_visible
from services.sammytv.repository import CatalogueRepository, CatalogueUnavailable

FAMILY = '10000000-0000-0000-0000-000000000001'
OTHER_FAMILY = '10000000-0000-0000-0000-000000000002'
MEMBER = '20000000-0000-0000-0000-000000000001'
PARENT = '20000000-0000-0000-0000-000000000002'
PROFILE = '30000000-0000-0000-0000-000000000001'
CHANNEL = '40000000-0000-0000-0000-000000000001'
CATEGORY = '50000000-0000-0000-0000-000000000001'
VIDEO = '60000000-0000-0000-0000-000000000001'
SECRET = 'sammytv-isolated-test-session-secret-123456789'


def approved_row():
    return dict(id=VIDEO, family_id=FAMILY, title='The coastal railway', description='A journey through the hills',
        duration_seconds=3661, provider='youtube', provider_video_id='AbCdEf123_-', status='approved',
        approved_at='2026-11-25T12:00:00Z', approved_by=PARENT, available=True, embeddable=True,
        age_restricted=False, is_live=False, moderation_notes='PRIVATE PARENT NOTES',
        channel=dict(id=CHANNEL, family_id=FAMILY, name='Rail Journal', enabled=True),
        categories=[dict(id=CATEGORY, name='Railways')])


class FakeRepository:
    """Fixtures model RPC filtering; injected bad rows test the Python boundary too."""
    def __init__(self):
        self.rows = [approved_row()]
        self.member_row = dict(id=MEMBER, family_id=FAMILY, role='viewer', active=True, session_version=1)
        self.profile_row = dict(id=PROFILE, family_id=FAMILY, member_id=MEMBER, nickname='S', enabled=True)
        self.family_row = dict(id=FAMILY, brand_name='SammyTV', enabled=True)
        self.calls = []
        self.force_bad_rows = False

    def member(self, family_id, member_id):
        self.calls.append(('member', family_id, member_id))
        return deepcopy(self.member_row) if family_id == FAMILY and member_id == MEMBER else None

    def profile(self, family_id, profile_id):
        return deepcopy(self.profile_row) if family_id == FAMILY and profile_id == PROFILE else None

    def family(self, family_id):
        return deepcopy(self.family_row) if family_id == FAMILY else None

    def categories(self, family_id):
        self.calls.append(('categories', family_id))
        return [dict(id=CATEGORY, name='Railways', slug='railways', position=0)] if family_id == FAMILY else []

    def channels(self, family_id):
        return [dict(id=CHANNEL, name='Rail Journal')] if self.rows and family_id == FAMILY else []

    def admin_videos(self, family_id, **filters):
        return []

    def videos(self, family_id, **filters):
        self.calls.append(('videos', family_id, filters))
        rows = deepcopy(self.rows)
        if not self.force_bad_rows:
            rows = [r for r in rows if is_visible(r, family_id)]
        if filters.get('video_id'):
            rows = [r for r in rows if r['id'] == filters['video_id']]
        if filters.get('channel_id'):
            rows = [r for r in rows if r['channel']['id'] == filters['channel_id']]
        if filters.get('category_id'):
            rows = [r for r in rows if any(c['id'] == filters['category_id'] for c in r['categories'])]
        if filters.get('query'):
            rows = [r for r in rows if filters['query'].lower() in (r['title'] + ' ' + r['description'] + ' ' + r['channel']['name']).lower()]
        offset, limit = filters.get('offset', 0), filters.get('limit', 48)
        return rows[offset:offset + limit]


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        self.env = patch.dict(os.environ, {'SAMMYTV_MODE': 'catalogue', 'SAMMYTV_SESSION_SECRET': SECRET,
            'SAMMYTV_YOUTUBE_PLAYBACK_ENABLED': '0'})
        self.env.start()
        self.adapter = patch('services.sammytv.views.CatalogueRepository', return_value=self.repo)
        self.adapter.start()
        self.client = app.test_client()
        self.sign_in()

    def tearDown(self):
        self.adapter.stop()
        self.env.stop()

    def sign_in(self, **overrides):
        now = datetime.now(timezone.utc)
        claims = dict(sub=MEMBER, family_id=FAMILY, profile_id=PROFILE, session_version=1,
            iss=ISSUER, aud=AUDIENCE, iat=now, exp=now + timedelta(hours=1))
        claims.update(overrides)
        self.client.set_cookie(COOKIE_NAME, jwt.encode(claims, SECRET, algorithm='HS256'))

    def test_catalogue_is_private_and_never_uses_sports_workspace_cookie(self):
        self.client.delete_cookie(COOKIE_NAME)
        self.client.set_cookie('cxms_sports_workspace_access', 'some-workspace-token')
        for path in ('/sammytv', '/sammytv/admin', '/sammytv/api/catalogue', f'/sammytv/api/videos/{VIDEO}/playback'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(b'The coastal railway', response.data)
        self.assertEqual(self.repo.calls, [])

    def test_valid_session_renders_only_database_catalogue(self):
        response = self.client.get('/sammytv')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'The coastal railway', response.data)
        self.assertNotIn(b'Along the coast:', response.data)
        self.assertIn(b'Railways', response.data)
        self.assertNotIn(b'Lucas Ivkovic', response.data)
        self.assertNotIn(b'PRIVATE PARENT NOTES', response.data)
        self.assertNotIn(b'AbCdEf123_-', response.data)

    def test_api_projection_omits_moderation_and_identity_data(self):
        response = self.client.get('/sammytv/api/catalogue')
        self.assertEqual(response.status_code, 200)
        row = response.json['videos'][0]
        self.assertEqual(row['duration'], '1:01:01')
        for key in ('family_id', 'approved_by', 'provider_video_id', 'moderation_notes', 'status'):
            self.assertNotIn(key, row)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['Vary'], 'Cookie')

    def test_forged_parent_claim_cannot_grant_parent_access(self):
        self.sign_in(role='parent')
        self.assertEqual(self.client.get('/sammytv/admin').status_code, 403)
        self.repo.member_row['role'] = 'parent'
        self.assertEqual(self.client.get('/sammytv/admin').status_code, 200)
        self.assertEqual(self.client.post('/sammytv/admin').status_code, 405)

    def test_expired_wrong_audience_and_cross_family_sessions_are_denied(self):
        for changes in ({'exp': datetime.now(timezone.utc) - timedelta(seconds=1)},
                        {'aud': 'sports-editorial'}, {'iss': 'another-app'},
                        {'family_id': OTHER_FAMILY}, {'profile_id': CHANNEL},
                        {'sub': 'not-a-uuid'}, {'session_version': 2},
                        {'exp': datetime.now(timezone.utc) + timedelta(days=2)}):
            with self.subTest(changes=changes):
                self.sign_in(**changes)
                self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 401)

    def test_tampered_token_and_missing_secret_fail_closed(self):
        self.client.set_cookie(COOKIE_NAME, 'invalid.jwt.token')
        self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 401)
        self.sign_in()
        with patch.dict(os.environ, {'SAMMYTV_SESSION_SECRET': ''}):
            self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 401)

    def test_deactivated_member_profile_and_family_are_denied(self):
        for target, key in ((self.repo.member_row, 'active'), (self.repo.profile_row, 'enabled'),
                            (self.repo.family_row, 'enabled')):
            with self.subTest(key=key):
                target[key] = False
                self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 401)
                target[key] = True
        self.repo.profile_row['member_id'] = PARENT
        self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 401)

    def test_caller_cannot_select_another_family_or_external_video(self):
        for key in ('family_id', 'profile_id', 'member_id', 'url', 'provider_video_id'):
            with self.subTest(key=key):
                self.assertEqual(self.client.get('/sammytv/api/catalogue', query_string={key: OTHER_FAMILY}).status_code, 400)
        self.assertEqual(self.client.get('/sammytv/api/videos/AbCdEf123_-').status_code, 404)
        self.assertEqual(self.client.get('/sammytv/api/videos/' + OTHER_FAMILY).status_code, 404)

    def test_filters_and_description_search_run_on_server(self):
        response = self.client.get('/sammytv/api/catalogue?q=hills&category=Railways')
        self.assertEqual(len(response.json['videos']), 1)
        calls = [c for c in self.repo.calls if c[0] == 'videos']
        self.assertEqual(calls[-1][1], FAMILY)
        self.assertEqual(calls[-1][2]['category_id'], CATEGORY)
        self.assertEqual(calls[-1][2]['query'], 'hills')
        self.assertEqual(self.client.get('/sammytv/api/catalogue?q=aircraft').json['videos'], [])
        self.assertEqual(self.client.get('/sammytv/api/catalogue?category=Disabled').status_code, 400)

    def test_pagination_is_bounded_and_stable(self):
        self.repo.rows = [dict(approved_row(), id=f'60000000-0000-0000-0000-{i:012d}') for i in range(1, 52)]
        response = self.client.get('/sammytv/api/catalogue?limit=2&offset=2')
        self.assertEqual(len(response.json['videos']), 2)
        self.assertTrue(response.json['has_more'])
        self.assertTrue(response.json['videos'][0]['id'].endswith('000000000003'))
        for query in ('limit=0', 'limit=49', 'offset=-1', 'offset=10001', 'limit=abc', 'q=' + 'a' * 121):
            self.assertEqual(self.client.get('/sammytv/api/catalogue?' + query).status_code, 400)
        page = self.client.get('/sammytv?category=Railways&q=railway')
        self.assertIn(b'Next page', page.data)
        self.assertIn(b'category=Railways', page.data)

    def test_pending_hidden_rejected_and_unavailable_videos_are_not_retrievable(self):
        changes = [{'status': status} for status in ('pending', 'hidden', 'rejected')]
        changes += [{'available': False}, {'embeddable': False}, {'age_restricted': True},
                    {'is_live': True}, {'approved_by': None}, {'approved_at': None}, {'family_id': OTHER_FAMILY}]
        for values in changes:
            with self.subTest(values=values):
                self.repo.rows = [dict(approved_row(), **values)]
                self.assertEqual(self.client.get('/sammytv/api/catalogue').json['videos'], [])
                self.assertEqual(self.client.get(f'/sammytv/watch/{VIDEO}').status_code, 404)
                self.assertEqual(self.client.get(f'/sammytv/api/videos/{VIDEO}/playback').status_code, 404)

    def test_bad_adapter_result_is_blocked_even_if_database_filter_fails(self):
        self.repo.force_bad_rows = True
        for values in ({'family_id': OTHER_FAMILY}, {'status': 'pending'}, {'provider_video_id': '../unapproved'}):
            with self.subTest(values=values):
                self.repo.rows = [dict(approved_row(), **values)]
                response = self.client.get('/sammytv/api/catalogue')
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b'The coastal railway', response.data)
        self.repo.rows = [approved_row()]
        self.repo.rows[0]['channel']['enabled'] = False
        self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 503)

    def test_malformed_catalogue_rows_are_a_safe_service_error(self):
        self.repo.force_bad_rows = True
        for values in ({'duration_seconds': None}, {'channel': 'invalid'},
                       {'categories': None}, {'provider_video_id': None}, {'title': None}):
            with self.subTest(values=values):
                self.repo.rows = [dict(approved_row(), **values)]
                self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code, 503)

    def test_youtube_requires_explicit_enablement_and_rechecks_approval(self):
        url = f'/sammytv/api/videos/{VIDEO}/playback'
        self.assertEqual(self.client.get(url).status_code, 403)
        with patch.dict(os.environ, {'SAMMYTV_YOUTUBE_PLAYBACK_ENABLED': '1'}):
            page = self.client.get(f'/sammytv/watch/{VIDEO}')
            self.assertIn(b'Load YouTube player', page.data)
            self.assertNotIn(b'<iframe', page.data)
            self.assertNotIn(b'AbCdEf123_-', page.data)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['embed_url'].startswith('https://www.youtube-nocookie.com/embed/AbCdEf123_-?'))
            self.assertIn('autoplay=0', response.json['embed_url'])
            self.assertEqual(response.headers['Referrer-Policy'], 'strict-origin-when-cross-origin')
            self.repo.rows[0]['status'] = 'hidden'
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_provider_failure_never_falls_back_to_demo_or_leaks_secrets(self):
        with patch.object(self.repo, 'videos', side_effect=CatalogueUnavailable('secret-key upstream body')):
            for path in ('/sammytv', '/sammytv/api/catalogue'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b'secret-key', response.data)
                self.assertNotIn(b'Along the coast', response.data)

    def test_database_content_is_escaped(self):
        self.repo.rows[0]['title'] = '<script>alert(1)</script>'
        response = self.client.get('/sammytv')
        self.assertNotIn(b'<script>alert(1)</script>', response.data)
        self.assertIn(b'&lt;script&gt;', response.data)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SAMMYTV_SUPABASE_URL': 'https://sammytv.example',
            'SAMMYTV_SUPABASE_SERVICE_ROLE_KEY': 'private-test-key'})
        self.env.start()
        self.repo = CatalogueRepository()

    def tearDown(self):
        self.env.stop()

    def test_rpc_uses_typed_payload_and_no_other_application_tables(self):
        query = "'),status.eq.pending%_"
        with patch('services.sammytv.repository.urlopen') as opener:
            opener.return_value.__enter__.return_value.read.return_value = b'[]'
            self.repo.videos(FAMILY, query=query, category_id=CATEGORY)
            req = opener.call_args[0][0]
            self.assertEqual(req.full_url, 'https://sammytv.example/rest/v1/rpc/sammytv_catalogue')
            self.assertEqual(json.loads(req.data)['p_query'], query)
            self.assertEqual(json.loads(req.data)['p_family_id'], FAMILY)
            self.assertEqual(req.headers['Authorization'], 'Bearer private-test-key')
            self.assertNotIn('private-test-key', req.full_url)
        with self.assertRaises(ValueError):
            self.repo._request('sports_editorial_submissions')

    def test_insecure_or_missing_configuration_never_sends_requests(self):
        self.repo.url = 'http://sammytv.example'
        with patch('services.sammytv.repository.urlopen') as opener:
            with self.assertRaises(CatalogueUnavailable):
                self.repo.categories(FAMILY)
            opener.assert_not_called()

    def test_upstream_errors_are_sanitised(self):
        for error in (URLError('private-test-key'), HTTPError('https://sammytv.example', 500, 'private-test-key', {}, None)):
            with patch('services.sammytv.repository.urlopen', side_effect=error):
                with self.assertRaises(CatalogueUnavailable) as context:
                    self.repo.videos(FAMILY)
                self.assertNotIn('private-test-key', str(context.exception))
