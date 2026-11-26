"""Parent workflow boundaries and metadata validation; no real network or accounts."""
from copy import deepcopy
import io
import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

from app import app
from services.sammytv.repository import CatalogueRepository, CatalogueUnavailable, ModerationConflict
from services.sammytv.youtube import MetadataUnavailable, VideoInputError, fetch_metadata, parse_video_url
import test_sammytv_catalogue as catalogue_tests
from test_sammytv_catalogue import (FakeRepository, FAMILY, OTHER_FAMILY,
    MEMBER, VIDEO, CATEGORY, approved_row)

PROVIDER_ID = 'AbCdEf123_-'
PROVIDER_CHANNEL = 'UC' + 'a' * 22
VERSION = '2026-11-25T12:00:00+00:00'


def metadata():
    row = approved_row()
    return {key: row[key] for key in ('provider_video_id', 'title', 'description',
        'duration_seconds', 'available', 'embeddable', 'age_restricted', 'is_live')} | {
        'provider_channel_id': PROVIDER_CHANNEL, 'channel_name': 'Rail Journal', 'broadcast_state': 'recording'}


def provider_item():
    return dict(id=PROVIDER_ID,
        snippet=dict(title='The coastal railway', description='A journey through the hills',
                     channelId=PROVIDER_CHANNEL, channelTitle='Rail Journal', liveBroadcastContent='none'),
        status=dict(privacyStatus='public', uploadStatus='processed', embeddable=True),
        contentDetails=dict(duration='PT1H1M1S', contentRating={}))


class MetadataTests(unittest.TestCase):
    def test_supported_single_video_urls_normalize_to_the_same_id(self):
        for url in (f'https://www.youtube.com/watch?v={PROVIDER_ID}&t=20',
                    f'https://youtu.be/{PROVIDER_ID}?si=sharing',
                    f'https://m.youtube.com/watch?v={PROVIDER_ID}',
                    f'https://youtube.com/shorts/{PROVIDER_ID}',
                    f'https://youtube.com/live/{PROVIDER_ID}',
                    f'https://youtube.com/embed/{PROVIDER_ID}'):
            with self.subTest(url=url):
                self.assertEqual(parse_video_url(url), PROVIDER_ID)

    def test_external_hosts_credentials_ports_playlist_and_malformed_urls_rejected(self):
        for url in ('http://localhost/admin', f'https://youtube.com.evil.test/watch?v={PROVIDER_ID}',
                    f'https://youtube.com@127.0.0.1/watch?v={PROVIDER_ID}',
                    f'https://youtube.com:443/watch?v={PROVIDER_ID}',
                    f'https://youtube.com/watch?v={PROVIDER_ID}&list=123',
                    f'https://youtube.com/watch?v={PROVIDER_ID}&v={PROVIDER_ID}',
                    f'https://youtu.be/{PROVIDER_ID}/other', 'https://youtube.com/@creator',
                    'https://youtube.com/watch?v=../../local', 'javascript:alert(1)',
                    f'https://youtube.com\n/watch?v={PROVIDER_ID}', 'https://youtube.com:bad/watch'):
            with self.subTest(url=url), self.assertRaises(VideoInputError):
                parse_video_url(url)

    def lookup(self, item):
        response = Mock()
        response.read.return_value = json.dumps({'items': [item]}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        return patch('services.sammytv.youtube.build_opener', return_value=opener), opener

    def test_fixed_host_lookup_uses_secret_header_and_extracts_metadata(self):
        lookup, opener = self.lookup(provider_item())
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='private-api-key'), lookup:
            self.assertEqual(fetch_metadata(PROVIDER_ID), metadata())
        req = opener.open.call_args.args[0]
        self.assertTrue(req.full_url.startswith('https://www.googleapis.com/youtube/v3/videos?'))
        self.assertNotIn('private-api-key', req.full_url)
        self.assertEqual(req.get_header('X-goog-api-key'), 'private-api-key')

    def test_missing_key_is_an_actionable_setup_error(self):
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY=''), self.assertRaisesRegex(MetadataUnavailable, 'SAMMYTV_YOUTUBE_API_KEY'):
            fetch_metadata(PROVIDER_ID)

    def test_ineligible_provider_flags_never_turn_into_eligible_metadata(self):
        variants = []
        item = provider_item(); item['status']['embeddable'] = False
        variants.append((item, 'embeddable', False))
        item = provider_item(); item['status']['privacyStatus'] = 'private'
        variants.append((item, 'available', False))
        item = provider_item(); item['contentDetails']['contentRating'] = {'ytRating': 'ytAgeRestricted'}
        variants.append((item, 'age_restricted', True))
        item = provider_item(); item['snippet']['liveBroadcastContent'] = 'live'
        variants.append((item, 'is_live', True))
        item = provider_item(); item['liveStreamingDetails'] = {'actualEndTime': '2026-01-01'}
        variants.append((item, 'is_live', True))
        item = provider_item(); item['contentDetails']['regionRestriction'] = {'allowed': ['GB']}
        variants.append((item, 'available', False))
        for item, key, expected in variants:
            lookup, _ = self.lookup(item)
            with self.subTest(key=key), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                self.assertIs(fetch_metadata(PROVIDER_ID)[key], expected)

    def test_malformed_and_missing_provider_fields_fail_closed(self):
        for field in ('status', 'contentDetails', 'snippet', 'id'):
            item = provider_item(); del item[field]
            lookup, _ = self.lookup(item)
            with self.subTest(field=field), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                with self.assertRaises(MetadataUnavailable):
                    fetch_metadata(PROVIDER_ID)

    def test_completed_livestream_is_an_eligible_recording(self):
        item = provider_item()
        item['liveStreamingDetails'] = dict(actualStartTime='2020-01-01T10:00:00Z',
                                            actualEndTime='2020-01-01T11:00:00Z')
        lookup, _ = self.lookup(item)
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
            result = fetch_metadata(PROVIDER_ID)
        self.assertIs(result['is_live'], False)
        self.assertIs(result['available'], True)
        self.assertIs(result['embeddable'], True)

    def test_public_active_camera_can_be_uploaded_with_zero_day_duration(self):
        item = provider_item()
        item['snippet']['liveBroadcastContent'] = 'live'
        item['status']['uploadStatus'] = 'uploaded'
        item['contentDetails']['duration'] = 'P0D'
        item['liveStreamingDetails'] = {'actualStartTime': '2020-01-01T11:00:00Z'}
        lookup, _ = self.lookup(item)
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
            result = fetch_metadata(PROVIDER_ID)
        self.assertIs(result['available'], True)
        self.assertEqual(result['broadcast_state'], 'live')
        self.assertIs(result['is_live'], True)
        self.assertEqual(result['duration_seconds'], 0)
        from services.sammytv.youtube import blocked_reasons
        self.assertTrue(blocked_reasons(result))  # Still needs explicit camera approval.
        self.assertEqual(blocked_reasons(result, allow_live_camera=True), [])

    def test_uploaded_recording_upcoming_or_unconfirmed_broadcast_is_not_ready(self):
        for state, streaming in (('none', None), ('upcoming', {}), ('none', {}),
                                 ('live', {'actualEndTime': '2020-01-01T11:00:00Z'}),
                                 ('live', None)):
            item = provider_item()
            item['snippet']['liveBroadcastContent'] = state
            item['status']['uploadStatus'] = 'uploaded'
            if streaming is not None or state == 'live':
                item['liveStreamingDetails'] = streaming
            lookup, _ = self.lookup(item)
            with self.subTest(state=state, streaming=streaming), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                self.assertIs(fetch_metadata(PROVIDER_ID)['available'], False)

    def test_live_state_cannot_override_failed_deleted_or_unknown_upload_status(self):
        for upload in ('failed', 'deleted', 'rejected', 'unknown', ''):
            item = provider_item()
            item['snippet']['liveBroadcastContent'] = 'live'
            item['status']['uploadStatus'] = upload
            lookup, _ = self.lookup(item)
            with self.subTest(upload=upload), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                self.assertIs(fetch_metadata(PROVIDER_ID)['available'], False)

    def test_uploaded_live_camera_still_requires_public_unrestricted_embedding(self):
        from services.sammytv.youtube import blocked_reasons
        for restriction in ('private', 'unlisted', 'embedding', 'region', 'age'):
            item = provider_item()
            item['snippet']['liveBroadcastContent'] = 'live'
            item['status']['uploadStatus'] = 'uploaded'
            if restriction in ('private','unlisted'):
                item['status']['privacyStatus'] = restriction
            elif restriction == 'embedding':
                item['status']['embeddable'] = False
            elif restriction == 'region':
                item['contentDetails']['regionRestriction'] = {'blocked': ['GB']}
            else:
                item['contentDetails']['contentRating'] = {'ytRating': 'ytAgeRestricted'}
            lookup, _ = self.lookup(item)
            with self.subTest(restriction=restriction), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                self.assertTrue(blocked_reasons(fetch_metadata(PROVIDER_ID), allow_live_camera=True))

    def test_active_upcoming_and_unconfirmed_broadcasts_stay_blocked(self):
        variants = [
            ('live', {'actualEndTime': '2020-01-01T11:00:00Z'}),
            ('upcoming', {'actualEndTime': '2020-01-01T11:00:00Z'}),
            ('none', {}), ('none', None), ('none', 'invalid'),
            ('none', {'actualEndTime': ''}), ('none', {'actualEndTime': None}),
            ('none', {'actualEndTime': '2020-01-01'}),
            ('none', {'actualEndTime': '2999-01-01T11:00:00Z'}),
            ('none', {'actualStartTime': '2020-01-02T11:00:00Z', 'actualEndTime': '2020-01-01T11:00:00Z'}),
        ]
        for state, streaming in variants:
            item = provider_item()
            item['snippet']['liveBroadcastContent'] = state
            item['liveStreamingDetails'] = streaming
            lookup, _ = self.lookup(item)
            with self.subTest(state=state, streaming=streaming), patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
                self.assertIs(fetch_metadata(PROVIDER_ID)['is_live'], True)

    def test_finished_stream_still_needs_embedding_permission(self):
        from services.sammytv.youtube import blocked_reasons
        item = provider_item()
        item['status']['embeddable'] = False
        item['liveStreamingDetails'] = {'actualEndTime': '2020-01-01T11:00:00Z'}
        lookup, _ = self.lookup(item)
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='key'), lookup:
            result = fetch_metadata(PROVIDER_ID)
        self.assertIs(result['is_live'], False)
        self.assertIs(result['embeddable'], False)
        self.assertIn('cannot play inside SammyTV', ' '.join(blocked_reasons(result)))

    def test_provider_errors_do_not_surface_key_or_response_body(self):
        error = HTTPError('https://provider', 403, 'private-api-key', {}, io.BytesIO(b'upstream-private-body'))
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY='private-api-key'), \
             patch('services.sammytv.youtube.build_opener') as builder:
            builder.return_value.open.side_effect = error
            with self.assertRaises(MetadataUnavailable) as caught:
                fetch_metadata(PROVIDER_ID)
        self.assertNotIn('private-api-key', str(caught.exception))
        self.assertNotIn('upstream-private-body', str(caught.exception))


class ParentRepository(FakeRepository):
    def __init__(self):
        super().__init__()
        self.member_row['role'] = 'parent'
        self.pending = dict(approved_row(), status='pending', updated_at=VERSION,
            category_links=[dict(category_id=CATEGORY)])
        self.pending['channel']['provider_channel_id'] = PROVIDER_CHANNEL
        self.import_video = Mock(return_value=dict(video_id=VIDEO, added=True))
        self.moderate_video = Mock(return_value=dict(video_id=VIDEO, status='approved'))
        self.approve_camera = Mock(return_value=dict(video_id=VIDEO, video_status='approved'))

    def admin_videos(self, family_id, **filters):
        self.calls.append(('admin_videos', family_id, filters))
        if family_id != FAMILY or filters.get('video_id', VIDEO) != VIDEO:
            return []
        return [deepcopy(self.pending)]


class ParentWorkflowTests(unittest.TestCase):
    sign_in = catalogue_tests.CatalogueTests.sign_in

    def setUp(self):
        from test_sammytv_catalogue import SECRET
        self.env = patch.dict(os.environ, SAMMYTV_MODE='catalogue', SAMMYTV_SESSION_SECRET=SECRET,
                              SAMMYTV_YOUTUBE_API_KEY='private-test-key')
        self.env.start()
        self.repo = ParentRepository()
        self.adapter = patch('services.sammytv.views.CatalogueRepository', return_value=self.repo)
        self.adapter.start()
        self.client = app.test_client()
        self.sign_in()

    def tearDown(self):
        self.adapter.stop()
        self.env.stop()

    def review_form(self):
        from html.parser import HTMLParser
        class HiddenParser(HTMLParser):
            def __init__(self):
                super().__init__(); self.values = {}
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'input' and values.get('type') == 'hidden':
                    self.values[values['name']] = values['value']
        response = self.client.get(f'/sammytv/admin/videos/{VIDEO}')
        self.assertEqual(response.status_code, 200)
        parser = HiddenParser(); parser.feed(response.text)
        return parser.values | dict(action='approve', category_ids=CATEGORY, reviewed='yes', notes='Parent notes')

    def test_parent_queue_and_review_do_not_load_external_content(self):
        for path in ('/sammytv/admin', f'/sammytv/admin/videos/{VIDEO}'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'The coastal railway', response.data)
            self.assertNotIn(b'<iframe', response.data)
            self.assertNotIn(b'private-test-key', response.data)
            self.assertEqual(response.headers['Cache-Control'], 'private, no-store')

    def test_viewers_cannot_read_or_mutate_parent_data_even_with_spoofed_claim(self):
        self.repo.member_row['role'] = 'viewer'
        self.sign_in(role='parent')
        with patch('services.sammytv.moderation.fetch_metadata') as lookup:
            for method, path in (('get', '/sammytv/admin'), ('post', '/sammytv/admin/videos'),
                                 ('get', f'/sammytv/admin/videos/{VIDEO}'),
                                 ('post', f'/sammytv/admin/videos/{VIDEO}')):
                self.assertEqual(getattr(self.client, method)(path).status_code, 403)
            lookup.assert_not_called()
        self.repo.import_video.assert_not_called(); self.repo.moderate_video.assert_not_called()
        self.assertNotIn(b'Parent area', self.client.get('/sammytv').data)

    def test_post_requires_csrf_before_provider_lookup(self):
        with patch('services.sammytv.moderation.fetch_metadata') as lookup:
            self.assertEqual(self.client.post('/sammytv/admin/videos').status_code, 400)
            self.assertEqual(self.client.post(f'/sammytv/admin/videos/{VIDEO}').status_code, 400)
            lookup.assert_not_called()

    def test_import_accepts_only_server_fetched_metadata_and_current_identity(self):
        form = self.review_form()
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata()) as lookup:
            response = self.client.post('/sammytv/admin/videos', data=dict(csrf_token=form['csrf_token'],
                video_url=f'https://youtu.be/{PROVIDER_ID}', family_id=OTHER_FAMILY,
                available='true', status='approved', title='Forged title'))
        self.assertEqual(response.status_code, 303)
        lookup.assert_called_once_with(PROVIDER_ID)
        viewer, imported = self.repo.import_video.call_args.args
        self.assertEqual(viewer['family_id'], FAMILY)
        self.assertEqual(viewer['session_version'], 1)
        self.assertEqual(imported['title'], metadata()['title'])
        self.repo.moderate_video.assert_not_called()

    def test_approval_requires_review_and_valid_family_category(self):
        form = self.review_form()
        for overrides in ({'reviewed': ''}, {'category_ids': OTHER_FAMILY}, {'category_ids': []}):
            with self.subTest(overrides=overrides), patch('services.sammytv.moderation.fetch_metadata') as lookup:
                response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form | overrides)
                self.assertEqual(response.status_code, 400)
                lookup.assert_not_called()
        self.repo.moderate_video.assert_not_called()

    def test_approval_rechecks_provider_and_passes_notes_and_categories(self):
        form = self.review_form()
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata()) as lookup:
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        self.assertEqual(response.status_code, 303)
        lookup.assert_called_once_with(PROVIDER_ID)
        self.assertEqual(self.repo.moderate_video.call_args.args[2], 'approve')
        self.assertEqual(self.repo.moderate_video.call_args.kwargs['category_ids'], [CATEGORY])
        self.assertEqual(self.repo.moderate_video.call_args.kwargs['notes'], 'Parent notes')

    def test_changed_provider_metadata_returns_to_review_without_approval(self):
        form = self.review_form()
        for changed in ({'title': 'A changed title'}, {'age_restricted': True}, {'is_live': True},
                        {'embeddable': False}, {'available': False}):
            with self.subTest(changed=changed), patch('services.sammytv.moderation.fetch_metadata', return_value=metadata() | changed):
                response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
                self.assertEqual(response.status_code, 303)
                self.assertIn('result=changed', response.location)
                self.assertEqual(self.repo.moderate_video.call_args.args[2], 'refresh')

    def test_recheck_refreshes_previously_blocked_recording_without_approving(self):
        self.repo.pending['is_live'] = True
        form = self.review_form() | dict(action='refresh')
        form.pop('reviewed'); form.pop('category_ids')
        def refresh(viewer, item, action, **kwargs):
            self.assertEqual(action, 'refresh')
            self.repo.pending.update(kwargs['metadata'], status='pending', updated_at='2026-11-25T13:00:00+00:00')
            return dict(video_id=VIDEO, status='pending')
        self.repo.moderate_video.side_effect = refresh
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata()):
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Video details updated', response.data)
        self.assertNotIn(b'This broadcast is live', response.data)
        self.assertEqual(self.repo.pending['status'], 'pending')
        self.repo.moderate_video.assert_called_once()

    def test_recheck_does_not_override_embedding_restriction_or_unapprove_unchanged_video(self):
        self.repo.pending['embeddable'] = False
        form = self.review_form() | dict(action='refresh')
        form.pop('reviewed')
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata() | dict(embeddable=False)):
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'cannot play inside SammyTV', response.data)
        self.repo.moderate_video.assert_not_called()

    def test_recheck_preserves_notes_and_rejects_stale_forms(self):
        form = self.review_form() | dict(action='refresh', notes='Retain my draft')
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata()):
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Retain my draft', response.data)
        self.repo.pending['updated_at'] = '2026-11-25T13:00:00+00:00'
        with patch('services.sammytv.moderation.fetch_metadata') as lookup:
            self.assertEqual(self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form).status_code, 409)
            lookup.assert_not_called()

    def test_removal_works_without_lookup_key_and_needs_no_approval_checkbox(self):
        form = self.review_form()
        with patch.dict(os.environ, SAMMYTV_YOUTUBE_API_KEY=''), \
             patch('services.sammytv.moderation.fetch_metadata') as lookup:
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}',
                data={k: v for k, v in (form | dict(action='hide')).items() if k not in ('reviewed', 'category_ids')})
        self.assertEqual(response.status_code, 303)
        self.assertIn('result=hidden', response.location)
        lookup.assert_not_called()
        self.assertEqual(self.repo.moderate_video.call_args.args[2], 'hide')

    def test_stale_or_tampered_reviews_cannot_undo_a_newer_action(self):
        form = self.review_form()
        for stale in (form | dict(review_token='forged'), form):
            self.repo.pending['updated_at'] = '2026-11-25T13:00:00+00:00'
            with patch('services.sammytv.moderation.fetch_metadata') as lookup:
                self.assertEqual(self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=stale).status_code, 409)
                lookup.assert_not_called()
        self.repo.moderate_video.assert_not_called()

    def test_concurrent_database_conflict_is_recoverable(self):
        form = self.review_form()
        self.repo.moderate_video.side_effect = ModerationConflict()
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata()):
            response = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        self.assertEqual(response.status_code, 409)
        self.assertIn(b'another tab', response.data)

    def test_other_family_and_invalid_video_identifiers_are_not_found(self):
        for video_id in (OTHER_FAMILY, 'not-a-uuid'):
            self.assertEqual(self.client.get('/sammytv/admin/videos/' + video_id).status_code, 404)
        self.repo.pending['family_id'] = OTHER_FAMILY
        self.assertEqual(self.client.get('/sammytv/admin/videos/' + VIDEO).status_code, 404)

    def test_preview_mode_cannot_import_or_moderate(self):
        with patch.dict(os.environ, SAMMYTV_MODE='preview'):
            self.assertEqual(self.client.get('/sammytv/admin').status_code, 200)
            self.assertEqual(self.client.post('/sammytv/admin/videos').status_code, 503)
            self.assertEqual(self.client.get('/sammytv/admin/videos/' + VIDEO).status_code, 503)
        self.repo.import_video.assert_not_called(); self.repo.moderate_video.assert_not_called()

    def test_parent_metadata_is_escaped_including_notes_and_titles(self):
        self.repo.pending['title'] = '<script>alert(1)</script>'
        self.repo.pending['moderation_notes'] = '</textarea><script>alert(2)</script>'
        response = self.client.get('/sammytv/admin/videos/' + VIDEO)
        self.assertNotIn(b'<script>alert', response.data)
        self.assertIn(b'&lt;script&gt;', response.data)

    def test_list_filters_and_pagination_are_bounded(self):
        self.assertEqual(self.client.get('/sammytv/admin?status=hidden&page=2').status_code, 200)
        call = [c for c in self.repo.calls if c[0] == 'admin_videos'][-1]
        self.assertEqual(call[1:], (FAMILY, dict(status='hidden', offset=24)))
        for query in ('page=0', 'page=418', 'status=unknown', 'page=oops'):
            self.assertEqual(self.client.get('/sammytv/admin?' + query).status_code, 400)


class ModerationTransportTests(unittest.TestCase):
    def test_rpc_errors_are_mapped_without_leaking_database_details(self):
        with patch.dict(os.environ, SAMMYTV_SUPABASE_URL='https://db.example',
                        SAMMYTV_SUPABASE_SERVICE_ROLE_KEY='secret'):
            repo = CatalogueRepository()
        body = io.BytesIO(json.dumps(dict(code='40001', message='private-database-details')).encode())
        with patch('services.sammytv.repository.urlopen', side_effect=HTTPError('https://db.example', 400, '', {}, body)):
            with self.assertRaises(ModerationConflict) as caught:
                repo._request('rpc/sammytv_moderate_video', payload={})
        self.assertNotIn('private', str(caught.exception))
