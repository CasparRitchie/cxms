"""Explicit camera approvals and fresh provider/approval checks. No live services."""
from copy import deepcopy
import os
import unittest
from unittest.mock import Mock, patch

from app import app
from services.sammytv.catalogue import is_visible, viewer_video
from services.sammytv.repository import CatalogueRepository, ModerationConflict
from services.sammytv.youtube import MetadataUnavailable, broadcast_state, duration_seconds
import test_sammytv_catalogue as catalogue_tests
import test_sammytv_moderation as parent_tests
from test_sammytv_catalogue import FAMILY, VIDEO, CATEGORY, OTHER_FAMILY


def camera_metadata():
    return parent_tests.metadata() | dict(is_live=True, broadcast_state='live', duration_seconds=0)


def camera_row():
    row = catalogue_tests.approved_row() | dict(is_live=True, live_camera=True,
        camera_video_id=parent_tests.PROVIDER_ID, camera_channel_id=parent_tests.PROVIDER_CHANNEL,
        updated_at=parent_tests.VERSION)
    row['channel']['provider_channel_id'] = parent_tests.PROVIDER_CHANNEL
    return row


class CameraEligibilityTests(unittest.TestCase):
    def test_live_duration_and_state_are_distinct_from_upcoming_or_unconfirmed(self):
        self.assertEqual(duration_seconds('P0D'), 0)
        self.assertEqual(duration_seconds('PT0S'), 0)
        for state in ('live', 'upcoming'):
            item = parent_tests.provider_item()
            item['snippet']['liveBroadcastContent'] = state
            self.assertEqual(broadcast_state(item), state)
        item = parent_tests.provider_item()
        item['liveStreamingDetails'] = {}
        self.assertEqual(broadcast_state(item), 'unconfirmed')
        for invalid in ('P', 'PT', 'P0DT', '', 'P-1D'):
            with self.subTest(invalid=invalid), self.assertRaises(MetadataUnavailable):
                duration_seconds(invalid)

    def test_category_name_alone_never_enables_live_playback(self):
        row = camera_row()
        row['categories'][0]['name'] = 'Live Cameras'
        row['live_camera'] = False
        self.assertFalse(is_visible(row, FAMILY))

    def test_camera_requires_exact_stream_creator_and_family_binding(self):
        self.assertTrue(is_visible(camera_row(), FAMILY))
        for changed in (dict(camera_video_id='Z' * 11), dict(camera_channel_id='UC' + 'b' * 22),
                        dict(camera_channel_id=''), dict(live_camera='true'), dict(is_live=False),
                        dict(family_id=OTHER_FAMILY), dict(embeddable=False), dict(age_restricted=True)):
            with self.subTest(changed=changed):
                self.assertFalse(is_visible(camera_row() | changed, FAMILY))

    def test_public_projection_marks_camera_but_omits_internal_bindings(self):
        public = viewer_video(camera_row())
        self.assertIs(public['is_camera'], True)
        self.assertEqual(public['duration'], 'LIVE')
        for key in ('live_camera', 'camera_video_id', 'camera_channel_id', 'updated_at', 'approved_by'):
            self.assertNotIn(key, public)
        self.assertNotIn('provider_channel_id', public['channel'])


class CameraApprovalTests(unittest.TestCase):
    setUp = parent_tests.ParentWorkflowTests.setUp
    tearDown = parent_tests.ParentWorkflowTests.tearDown
    sign_in = parent_tests.ParentWorkflowTests.sign_in
    review_form = parent_tests.ParentWorkflowTests.review_form

    def camera_form(self):
        self.repo.pending.update(is_live=True, duration_seconds=0)
        return self.review_form() | dict(action='approve_camera', reviewed='', camera_reviewed='yes')

    def post(self, form, metadata=None):
        with patch('services.sammytv.moderation.fetch_metadata', return_value=metadata or camera_metadata()) as lookup:
            result = self.client.post(f'/sammytv/admin/videos/{VIDEO}', data=form)
        return result, lookup

    def test_explicit_camera_review_passes_fresh_metadata_and_current_parent(self):
        form = self.camera_form()
        result, lookup = self.post(form)
        self.assertEqual(result.status_code, 303)
        lookup.assert_called_once_with(parent_tests.PROVIDER_ID)
        viewer, row, metadata, categories = self.repo.approve_camera.call_args.args
        self.assertEqual(viewer['family_id'], FAMILY)
        self.assertEqual(row['updated_at'], parent_tests.VERSION)
        self.assertEqual(metadata, camera_metadata())
        self.assertEqual(categories, [CATEGORY])
        self.repo.moderate_video.assert_not_called()

    def test_camera_needs_its_own_confirmation_valid_categories_and_csrf(self):
        form = self.camera_form()
        for changes in (dict(camera_reviewed='', reviewed='yes'), dict(category_ids=OTHER_FAMILY),
                        dict(category_ids=[]), dict(csrf_token='')):
            with self.subTest(changes=changes):
                result, lookup = self.post(form | changes)
                self.assertEqual(result.status_code, 400)
                lookup.assert_not_called()
        self.repo.approve_camera.assert_not_called()

    def test_ordinary_approval_still_rejects_live_stream(self):
        form = self.camera_form() | dict(action='approve', reviewed='yes')
        result, _ = self.post(form)
        self.assertEqual(result.status_code, 400)
        self.repo.approve_camera.assert_not_called()
        self.repo.moderate_video.assert_not_called()

    def test_upcoming_unconfirmed_and_ended_streams_cannot_use_camera_approval(self):
        form = self.camera_form()
        for state in ('upcoming', 'unconfirmed', 'ended', 'recording', None):
            with self.subTest(state=state):
                result, _ = self.post(form, camera_metadata() | dict(broadcast_state=state))
                self.assertEqual(result.status_code, 400)
        self.repo.approve_camera.assert_not_called()

    def test_other_restrictions_cannot_be_bypassed_by_camera_approval(self):
        form = self.camera_form()
        for key, value in (('available', False), ('embeddable', False), ('age_restricted', True)):
            self.repo.pending[key] = value
            with self.subTest(key=key):
                result, _ = self.post(form, camera_metadata() | {key: value})
                self.assertEqual(result.status_code, 400)
            self.repo.pending[key] = camera_metadata()[key]
        self.repo.approve_camera.assert_not_called()

    def test_creator_change_rejected_and_content_change_returns_to_review(self):
        form = self.camera_form()
        result, _ = self.post(form, camera_metadata() | dict(provider_channel_id='UC' + 'b' * 22))
        self.assertEqual(result.status_code, 400)
        result, _ = self.post(form, camera_metadata() | dict(title='Changed camera'))
        self.assertEqual(result.status_code, 303)
        self.assertIn('result=changed', result.location)
        self.assertEqual(self.repo.moderate_video.call_args.args[2], 'refresh')
        self.repo.approve_camera.assert_not_called()

    def test_growing_duration_does_not_prevent_reviewed_camera_approval(self):
        result, _ = self.post(self.camera_form(), camera_metadata() | dict(duration_seconds=120))
        self.assertEqual(result.status_code, 303)
        self.repo.approve_camera.assert_called_once()
        self.repo.moderate_video.assert_not_called()

    def test_stale_review_and_revoked_viewer_cannot_approve_camera(self):
        form = self.camera_form()
        self.repo.pending['updated_at'] = '2026-11-25T15:00:00Z'
        result, lookup = self.post(form)
        self.assertEqual(result.status_code, 409)
        lookup.assert_not_called()
        self.repo.member_row['role'] = 'viewer'
        result, lookup = self.post(form)
        self.assertEqual(result.status_code, 403)
        lookup.assert_not_called()
        self.repo.approve_camera.assert_not_called()

    def test_repository_camera_rpc_is_bound_to_review_version_and_confirmation(self):
        repo = CatalogueRepository()
        repo._request = Mock(return_value=[dict(video_id=VIDEO, video_status='approved')])
        viewer = dict(family_id=FAMILY, member_id='parent-id', session_version=3)
        repo.approve_camera(viewer, camera_row(), camera_metadata(), [CATEGORY], notes='Reviewed')
        name = repo._request.call_args.args[0]
        args = repo._request.call_args.kwargs['payload']
        self.assertEqual(name, 'rpc/sammytv_approve_camera')
        self.assertEqual(args['p_session_version'], 3)
        self.assertEqual(args['p_expected_updated_at'], parent_tests.VERSION)
        self.assertIs(args['p_confirmed'], True)


class CameraPlaybackTests(unittest.TestCase):
    setUp = catalogue_tests.CatalogueTests.setUp
    tearDown = catalogue_tests.CatalogueTests.tearDown
    sign_in = catalogue_tests.CatalogueTests.sign_in

    def playback(self):
        return self.client.get(f'/sammytv/api/videos/{VIDEO}/playback')

    def enable(self):
        self.repo.rows = [camera_row()]
        os.environ['SAMMYTV_YOUTUBE_PLAYBACK_ENABLED'] = '1'

    def test_camera_checks_provider_each_click_then_rechecks_database_approval(self):
        self.enable()
        with patch('services.sammytv.views.fetch_metadata', return_value=camera_metadata()) as lookup:
            for _ in range(2):
                response = self.playback()
                self.assertEqual(response.status_code, 200)
                self.assertIn('/embed/' + parent_tests.PROVIDER_ID, response.json['embed_url'])
            self.assertEqual(lookup.call_count, 2)
        self.assertEqual(len([call for call in self.repo.calls if call[0] == 'videos']), 4)

    def test_offline_changed_or_restricted_camera_never_returns_player(self):
        self.enable()
        for change in (dict(broadcast_state='upcoming'), dict(broadcast_state='ended', is_live=False),
                       dict(available=False), dict(embeddable=False), dict(age_restricted=True),
                       dict(provider_video_id='Z' * 11), dict(provider_channel_id='UC' + 'b' * 22),
                       dict(title='Another view'), dict(description='New description')):
            with self.subTest(change=change), patch('services.sammytv.views.fetch_metadata', return_value=camera_metadata() | change):
                response = self.playback()
                self.assertEqual(response.status_code, 410)
                self.assertEqual(response.json['error'], 'camera_offline')
                self.assertNotIn('embed_url', response.json)

    def test_provider_failure_shows_fixed_message_without_credentials(self):
        self.enable()
        with patch('services.sammytv.views.fetch_metadata', side_effect=MetadataUnavailable('private-key')):
            response = self.playback()
        self.assertEqual(response.status_code, 410)
        self.assertNotIn('private-key', response.text)

    def test_removal_during_provider_check_prevents_playback(self):
        self.enable()
        def revoke(_):
            self.repo.rows[0]['status'] = 'hidden'
            return camera_metadata()
        with patch('services.sammytv.views.fetch_metadata', side_effect=revoke):
            self.assertEqual(self.playback().status_code, 404)

    def test_reapproval_during_provider_check_requires_another_click(self):
        self.enable()
        def change(_):
            self.repo.rows[0]['updated_at'] = '2026-11-25T15:00:00Z'
            return camera_metadata()
        with patch('services.sammytv.views.fetch_metadata', side_effect=change):
            self.assertEqual(self.playback().status_code, 410)

    def test_disabled_playback_and_recordings_do_not_request_live_metadata(self):
        self.repo.rows = [camera_row()]
        with patch('services.sammytv.views.fetch_metadata') as lookup:
            self.assertEqual(self.playback().status_code, 403)
            self.repo.rows = [catalogue_tests.approved_row()]
            os.environ['SAMMYTV_YOUTUBE_PLAYBACK_ENABLED'] = '1'
            self.assertEqual(self.playback().status_code, 200)
            lookup.assert_not_called()

    def test_camera_card_uses_live_badge_without_external_player_at_page_load(self):
        self.enable()
        response = self.client.get('/sammytv')
        self.assertEqual(response.status_code, 200)
        self.assertIn('LIVE CAMERA', response.text)
        self.assertNotIn('<iframe', response.text)
