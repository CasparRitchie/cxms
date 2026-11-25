"""Bulk-import restart behaviour and editable category access boundaries."""
from copy import deepcopy
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.sammytv.bulk_import import import_links, normalize_links, select_parent
from services.sammytv.categories import category_name, suggest_categories
from services.sammytv.repository import ModerationDenied, ModerationInvalid
from services.sammytv.youtube import VideoInputError
from test_sammytv_catalogue import CATEGORY, FAMILY, MEMBER, OTHER_FAMILY, VIDEO
import test_sammytv_moderation as parent_tests


class BulkImportTests(unittest.TestCase):
    def test_supplied_list_has_22_distinct_valid_video_ids(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/data/sammytv_links_2026-11-25.txt'
        entries, errors, duplicates = normalize_links(path.read_text().splitlines())
        self.assertEqual((len(entries), errors, duplicates), (22, [], 0))
        self.assertEqual(entries[3]['video_id'], 'heFNx_-wkh4')

    def test_sharing_urls_are_deduplicated_by_id_and_bad_urls_are_reported(self):
        entries, errors, duplicates = normalize_links([
            '# a comment', 'https://youtu.be/AbCdEf123_-?si=share',
            'https://youtube.com/shorts/AbCdEf123_-', 'https://example.test/private', ''])
        self.assertEqual((len(entries), len(errors), duplicates), (1, 1, 1))
        self.assertEqual(errors[0]['line'], 4)
        with self.assertRaisesRegex(ValueError, '250'):
            normalize_links(['https://youtu.be/AbCdEf123_-'] * 251)

    def test_batch_continues_after_a_bad_link_and_preserves_existing_approval(self):
        repo = Mock()
        repo.categories.return_value = []
        repo.import_video.side_effect = [dict(video_id=VIDEO, added=True), dict(video_id=VIDEO, added=False)]
        parent = dict(family_id=FAMILY, member_id=MEMBER, session_version=1)
        entries = [dict(video_id='AbCdEf123_-'), dict(video_id='BbCdEf123_-'), dict(video_id='CbCdEf123_-')]
        with patch('services.sammytv.bulk_import.fetch_metadata', side_effect=[parent_tests.metadata(), VideoInputError('Video unavailable.'), parent_tests.metadata()]):
            results = import_links(repo, parent, entries)
        self.assertEqual([r['outcome'] for r in results], ['added', 'failed', 'exists'])
        self.assertEqual(repo.import_video.call_count, 2)
        repo.moderate_video.assert_not_called()
        repo.manage_category.assert_not_called()

    def test_dry_run_does_not_write_videos_or_categories(self):
        repo = Mock(); repo.categories.return_value = []
        with patch('services.sammytv.bulk_import.fetch_metadata', return_value=parent_tests.metadata()):
            results = import_links(repo, dict(family_id=FAMILY), [dict(video_id='AbCdEf123_-')], dry_run=True)
        self.assertEqual(results[0]['outcome'], 'checked')
        self.assertTrue(results[0]['suggestions'])
        repo.import_video.assert_not_called(); repo.manage_category.assert_not_called()

    def test_parent_revocation_stops_batch_immediately(self):
        repo = Mock(); repo.categories.return_value = []; repo.import_video.side_effect = ModerationDenied()
        with patch('services.sammytv.bulk_import.fetch_metadata', return_value=parent_tests.metadata()) as lookup:
            with self.assertRaises(ModerationDenied):
                import_links(repo, dict(family_id=FAMILY), [dict(video_id='AbCdEf123_-')] * 2)
        self.assertEqual(lookup.call_count, 1)

    def test_multiple_parents_require_an_explicit_choice(self):
        repo = Mock()
        repo.import_parents.return_value = [dict(id=MEMBER), dict(id=OTHER_FAMILY)]
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            select_parent(repo)

    def test_selected_parent_is_current_active_and_has_an_enabled_family(self):
        repo = Mock()
        row = dict(id=MEMBER, family_id=FAMILY, active=True, role='parent', session_version=3)
        repo.import_parents.return_value = [row]
        repo.family.return_value = dict(id=FAMILY, enabled=True)
        self.assertEqual(select_parent(repo, MEMBER)['session_version'], 3)
        for change in ({'role': 'viewer'}, {'active': False}, {'id': OTHER_FAMILY}):
            repo.import_parents.return_value = [row | change]
            with self.subTest(change=change), self.assertRaises(ValueError):
                select_parent(repo, MEMBER)


class SuggestionTests(unittest.TestCase):
    def test_names_are_flexible_normalized_and_reserved_names_are_rejected(self):
        self.assertEqual(category_name('  Space   travel & rockets  '), 'Space travel & rockets')
        self.assertEqual(category_name('Avions et aéroports'), 'Avions et aéroports')
        for name in ('ALL', 'Favourites', '', 'x' * 61, 'Bad\x00name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                category_name(name)

    def test_suggestions_use_video_metadata_and_existing_custom_categories(self):
        categories = [dict(id=CATEGORY, name='Steam adventures')]
        video = dict(title='Steam adventures on the railway', description='Model trains and Hornby', channel_name='Coastal Rail Films')
        suggestions = suggest_categories(video, categories)
        names = [s['name'] for s in suggestions]
        self.assertIn('Steam adventures', names)
        self.assertIn('Trains', names)
        self.assertIn('Model railways', names)
        self.assertIn('Coastal Rail Films', names)
        self.assertEqual(next(s for s in suggestions if s['name'] == 'Steam adventures')['category_id'], CATEGORY)
        self.assertEqual(len(names), len(set(names)))

    def test_creator_is_not_forced_to_a_fixed_topic_and_bad_names_are_ignored(self):
        self.assertEqual(suggest_categories(dict(title='An afternoon', channel_name='A new creator'))[-1]['name'], 'A new creator')
        self.assertEqual(suggest_categories(dict(title='', channel_name='All')), [])


class CategoryParentTests(unittest.TestCase):
    setUp = parent_tests.ParentWorkflowTests.setUp
    tearDown = parent_tests.ParentWorkflowTests.tearDown
    sign_in = parent_tests.ParentWorkflowTests.sign_in
    review_form = parent_tests.ParentWorkflowTests.review_form

    def setup_categories(self):
        self.category_rows = [dict(id=CATEGORY, family_id=FAMILY, name='Railways', slug='railways', position=0, enabled=True)]
        self.repo.admin_categories = Mock(side_effect=lambda family: deepcopy(self.category_rows))
        self.repo.manage_category = Mock(return_value=dict(category_id=CATEGORY, category_name='Railways', enabled=True, category_position=0))

    def test_manager_renders_categories_for_the_current_family(self):
        self.setup_categories()
        response = self.client.get('/sammytv/admin/categories')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Create a category', response.data)
        self.assertIn(b'Archive', response.data)
        self.repo.admin_categories.assert_called_once_with(FAMILY)
        self.category_rows[0]['family_id'] = OTHER_FAMILY
        self.assertEqual(self.client.get('/sammytv/admin/categories').status_code, 503)

    def test_viewer_and_preview_cannot_manage_categories(self):
        self.setup_categories()
        self.repo.member_row['role'] = 'viewer'
        self.assertEqual(self.client.get('/sammytv/admin/categories').status_code, 403)
        self.assertEqual(self.client.post('/sammytv/admin/categories').status_code, 403)
        with patch.dict('os.environ', SAMMYTV_MODE='preview'):
            self.assertEqual(self.client.get('/sammytv/admin/categories').status_code, 503)
        self.repo.manage_category.assert_not_called()

    def test_category_writes_need_csrf_and_do_not_accept_family_selectors(self):
        self.setup_categories()
        self.assertEqual(self.client.post('/sammytv/admin/categories', data=dict(action='create', name='Custom')).status_code, 400)
        token = self.review_form()['csrf_token']
        response = self.client.post('/sammytv/admin/categories', data=dict(csrf_token=token, action='create', name='  Any   interest  ', family_id=OTHER_FAMILY))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.repo.manage_category.call_args.args[0]['family_id'], FAMILY)
        self.assertEqual(self.repo.manage_category.call_args.kwargs['name'], 'Any interest')

    def test_save_archive_and_restore_are_explicit_actions(self):
        self.setup_categories()
        token = self.review_form()['csrf_token']
        for action in ('save', 'archive', 'restore'):
            response = self.client.post('/sammytv/admin/categories', data=dict(csrf_token=token,
                action=action, category_id=CATEGORY, name='New name', position='12'))
            self.assertEqual(response.status_code, 303)
            self.assertEqual(self.repo.manage_category.call_args.args[1], action)
            self.assertEqual(self.repo.manage_category.call_args.kwargs['category_id'], CATEGORY)
        self.repo.moderate_video.assert_not_called()

    def test_reserved_name_and_invalid_order_cannot_be_saved(self):
        self.setup_categories()
        token = self.review_form()['csrf_token']
        for changes in ({'name': 'All'}, {'position': '-1'}, {'position': 'abc'}):
            response = self.client.post('/sammytv/admin/categories', data=dict(csrf_token=token, action='create', name='Custom') | changes)
            self.assertEqual(response.status_code, 400)
        self.repo.manage_category.assert_not_called()

    def test_create_from_review_preserves_notes_and_selections_without_approval(self):
        self.setup_categories()
        form = self.review_form() | dict(action='add_category', new_category_name='Space journeys', notes='Keep this note')
        response = self.client.post('/sammytv/admin/videos/' + VIDEO, data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Keep this note', response.data)
        self.assertIn(b'Category added and selected', response.data)
        self.repo.moderate_video.assert_not_called()
        self.assertEqual(self.repo.manage_category.call_args.kwargs['name'], 'Space journeys')

    def test_metadata_suggestion_can_be_selected_without_claiming_video_review(self):
        self.setup_categories()
        form = self.review_form()
        form.pop('action'); form.pop('reviewed')
        response = self.client.post('/sammytv/admin/videos/' + VIDEO, data=form | dict(suggested_category='Rail Journal'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repo.manage_category.call_args.kwargs['name'], 'Rail Journal')
        self.repo.moderate_video.assert_not_called()

    def test_archived_name_conflict_is_actionable(self):
        self.setup_categories()
        self.repo.manage_category.side_effect = ModerationInvalid()
        form = self.review_form() | dict(action='add_category', new_category_name='Archived category')
        response = self.client.post('/sammytv/admin/videos/' + VIDEO, data=form)
        self.assertEqual(response.status_code, 400)


class BulkCommandTests(unittest.TestCase):
    def test_command_redacts_provider_terminal_controls(self):
        from scripts.import_sammytv import terminal_text
        self.assertNotIn('\x1b', terminal_text('Untrusted\x1b[31mTitle\nNext line'))

    def test_command_dry_run_uses_the_checked_parent_and_supplied_list(self):
        from scripts.import_sammytv import main
        root = Path(__file__).resolve().parents[1]
        parent = dict(family_id=FAMILY, member_id=MEMBER, session_version=1)
        with patch('scripts.import_sammytv.CatalogueRepository'), \
             patch('scripts.import_sammytv.select_parent', return_value=parent), \
             patch('scripts.import_sammytv.import_links', return_value=[]) as importer, \
             patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['--file', str(root / 'scripts/data/sammytv_links_2026-11-25.txt'), '--dry-run']), 0)
        self.assertEqual(len(importer.call_args.args[2]), 22)
        self.assertTrue(importer.call_args.kwargs['dry_run'])
