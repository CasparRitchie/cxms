"""Family/account HTTP boundaries; real SQL invariants have staging checks."""
from copy import deepcopy
import os
import unittest
from unittest.mock import Mock, patch

import jwt
from app import app
from services.sammytv.auth import COOKIE_NAME
from services.sammytv.credentials import digest_code, password_hash, password_matches
from services.sammytv.repository import ModerationConflict, ModerationDenied, ModerationInvalid
import test_sammytv_catalogue as catalogue_tests
from test_sammytv_catalogue import FAMILY, OTHER_FAMILY, MEMBER, PROFILE, SECRET

PASSWORD = 'three words for trains'
HASH = password_hash(PASSWORD)
CHILD = '70000000-0000-0000-0000-000000000001'
VERSION = '2026-11-26T12:00:00Z'
RECORD = dict(member_id=MEMBER,family_id=FAMILY,profile_id=PROFILE,session_version=1)


class FamilyRepository(catalogue_tests.FakeRepository):
    def __init__(self):
        super().__init__()
        self.children = [dict(child_id=CHILD,username='railfan',nickname='Rail fan',account_status='pending',updated_at=VERSION)]
        self.auth_limit = Mock(return_value=True)
        self.child_credentials = Mock(return_value=dict(child_id=MEMBER,password_hash=HASH))
        self.child_session = Mock(return_value=RECORD)
        self.request_child = Mock(return_value=True)
        self.manage_child = Mock(return_value=[dict(child_id=CHILD)])
        self.create_registration_code = Mock()
        self.create_parent_invite = Mock()
        self.verify_parent = Mock(return_value=MEMBER)
        self.provision_parent = Mock(return_value=RECORD)
        self.existing_parent = Mock(return_value=RECORD)
        self.accept_parent_invite = Mock(return_value=RECORD)

    def family_children(self,viewer):
        return deepcopy(self.children)

    def family_parents(self,viewer):
        return [dict(parent_id=MEMBER,nickname='Parent')]


class AccountTests(unittest.TestCase):
    sign_in = catalogue_tests.CatalogueTests.sign_in

    def setUp(self):
        self.env = patch.dict(os.environ,SAMMYTV_MODE='catalogue',SAMMYTV_SESSION_SECRET=SECRET,
                              SAMMYTV_PARENT_EMAILS='parent@example.test')
        self.env.start()
        self.repo = FamilyRepository()
        self.adapter = patch('services.sammytv.views.CatalogueRepository',return_value=self.repo)
        self.adapter.start()
        self.client = app.test_client()

    def tearDown(self):
        self.adapter.stop(); self.env.stop()

    def csrf(self,path='/sammytv/signin'):
        response = self.client.get(path)
        self.assertEqual(response.status_code,200)
        return self.client.get_cookie('sammytv_csrf',path='/sammytv').value

    def login_child(self,**changes):
        form = dict(csrf_token=self.csrf(),role='child',username='RAILFAN',password=PASSWORD)
        return self.client.post('/sammytv/signin',data=form|changes)

    def parent(self):
        self.repo.member_row['role']='parent'
        self.sign_in()

    def family_form(self):
        from html.parser import HTMLParser
        class Inputs(HTMLParser):
            def __init__(self):
                super().__init__(); self.inputs={}
            def handle_starttag(self,tag,attrs):
                values=dict(attrs)
                if tag=='input' and values.get('type')=='hidden':
                    self.inputs[values['name']]=values.get('value','')
        response=self.client.get('/sammytv/admin/family')
        self.assertEqual(response.status_code,200)
        parser=Inputs(); parser.feed(response.text)
        return {k:v for k,v in parser.inputs.items() if k in ('csrf_token','review_token')}

    def test_root_redirects_to_child_parent_login_without_any_catalogue_reads(self):
        response=self.client.get('/sammytv',follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertIn('I’m watching',response.text); self.assertIn('I’m a parent',response.text)
        self.assertIn('Username',response.text); self.assertNotIn('The coastal railway',response.text)
        self.assertEqual(self.repo.calls,[])
        self.assertNotIn('<iframe',response.text)

    def test_already_signed_in_root_and_signin_go_to_collection(self):
        self.sign_in()
        self.assertEqual(self.client.get('/sammytv').status_code,200)
        response=self.client.get('/sammytv/signin')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.location,'/sammytv')

    def test_expired_cookie_returns_login_while_api_returns_401(self):
        self.client.set_cookie(COOKIE_NAME,'invalid.token')
        self.assertEqual(self.client.get('/sammytv').status_code,302)
        self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code,401)

    def test_child_login_normalises_username_and_rechecks_hash_snapshot(self):
        response=self.login_child(family_id=OTHER_FAMILY,member_id='forged',role_claim='parent')
        self.assertEqual(response.status_code,302)
        self.repo.child_credentials.assert_called_once_with('railfan')
        self.repo.child_session.assert_called_once_with(MEMBER,HASH)
        self.assertNotIn(HASH,response.text)
        token=self.client.get_cookie(COOKIE_NAME,path='/sammytv').value
        claims=jwt.decode(token,SECRET,algorithms=['HS256'],audience='sammytv',issuer='cxms:sammytv')
        self.assertEqual(claims['family_id'],FAMILY)
        self.assertNotIn('role',claims)
        self.assertEqual(self.client.get('/sammytv/admin/family').status_code,403)

    def test_wrong_missing_pending_and_disabled_child_logins_share_generic_response(self):
        wrong=self.login_child(password='the wrong password')
        self.repo.child_credentials.return_value=None
        missing=self.login_child()
        self.assertEqual(wrong.status_code,401); self.assertEqual(missing.status_code,401)
        self.assertIn('Check your username and password',wrong.text)
        self.assertIn('Check your username and password',missing.text)
        self.repo.child_session.assert_not_called()
        self.assertIsNone(self.client.get_cookie(COOKIE_NAME,path='/sammytv'))

    def test_reset_or_disable_during_password_check_prevents_login(self):
        self.repo.child_session.return_value=None
        self.assertEqual(self.login_child().status_code,401)

    def test_persistent_throttle_runs_before_password_check(self):
        self.repo.auth_limit.return_value=False
        response=self.login_child()
        self.assertEqual(response.status_code,429)
        self.repo.child_credentials.assert_not_called()
        self.assertNotIn(PASSWORD,response.text)

    def test_throttle_buckets_are_keyed_and_ignore_spoofed_leftmost_proxy_hop(self):
        token=self.csrf()
        for value in ('spoofed, 192.0.2.9','different, 192.0.2.9'):
            self.client.post('/sammytv/signin',headers={'X-Forwarded-For':value},
                data=dict(csrf_token=token,role='child',username='railfan',password='wrong'))
        calls=self.repo.auth_limit.call_args_list
        self.assertEqual(calls[0].args[0],calls[2].args[0])
        self.assertEqual(len(calls[0].args[0]),64)
        self.assertNotIn('railfan',repr(calls)); self.assertNotIn('192.0.2.9',repr(calls))

    def test_no_auth_writes_without_csrf(self):
        for path in ('/sammytv/signin','/sammytv/register','/sammytv/pair'):
            self.assertEqual(self.client.post(path).status_code,400)
        self.repo.auth_limit.assert_not_called(); self.repo.request_child.assert_not_called()

    def test_large_auth_bodies_are_rejected_before_provider_or_hash_work(self):
        response=self.client.post('/sammytv/signin',data={'password':'x'*17000})
        self.assertEqual(response.status_code,413)
        self.repo.verify_parent.assert_not_called()

    def test_register_only_creates_pending_request_without_session_or_family_selectors(self):
        token=self.csrf('/sammytv/register')
        code='a'*32
        response=self.client.post('/sammytv/register',data=dict(csrf_token=token,family_code=code,
            username='New_User',nickname='Railway fan',password=PASSWORD,password_confirm=PASSWORD,family_id=OTHER_FAMILY))
        self.assertEqual(response.status_code,200)
        self.assertIn('Your parent has the next step',response.text)
        args=self.repo.request_child.call_args.args
        self.assertEqual(args[:3],(digest_code(code),'new_user','Railway fan'))
        self.assertTrue(password_matches(args[3],PASSWORD))
        self.assertIsNone(self.client.get_cookie(COOKIE_NAME,path='/sammytv'))
        self.assertNotIn(PASSWORD,response.text); self.assertNotIn(code,response.text)

    def test_registration_validates_code_username_password_confirmation(self):
        token=self.csrf('/sammytv/register')
        form=dict(csrf_token=token,family_code='a'*32,username='new_user',nickname='Viewer',password=PASSWORD,password_confirm=PASSWORD)
        for change in (dict(family_code='123'),dict(username='bad user'),dict(nickname=''),
                       dict(password='short',password_confirm='short'),dict(password_confirm='different')):
            with self.subTest(change=change):
                self.assertEqual(self.client.post('/sammytv/register',data=form|change).status_code,400)
        self.repo.request_child.assert_not_called()

    def test_invalid_family_code_or_duplicate_login_does_not_sign_in(self):
        token=self.csrf('/sammytv/register')
        form=dict(csrf_token=token,family_code='a'*32,username='new_user',nickname='Viewer',password=PASSWORD,password_confirm=PASSWORD)
        self.repo.request_child.return_value=False
        self.assertEqual(self.client.post('/sammytv/register',data=form).status_code,400)
        self.repo.request_child.side_effect=ModerationInvalid()
        self.assertEqual(self.client.post('/sammytv/register',data=form).status_code,400)
        self.assertIsNone(self.client.get_cookie(COOKIE_NAME,path='/sammytv'))

    def test_unknown_parent_cannot_self_assign_a_role_or_create_family(self):
        self.repo.existing_parent.return_value=None
        token=self.csrf('/sammytv/signin?role=parent')
        result=self.client.post('/sammytv/signin',data=dict(csrf_token=token,role='parent',
            email='unknown@example.test',password=PASSWORD,family_id=FAMILY))
        self.assertEqual(result.status_code,401)
        self.repo.provision_parent.assert_not_called()

    def test_invited_parent_uses_verified_identity_and_exact_invitation_digest(self):
        token=self.csrf('/sammytv/signin?role=parent')
        result=self.client.post('/sammytv/signin',data=dict(csrf_token=token,role='parent',
            email='invited@example.test',password=PASSWORD,invitation='b'*32))
        self.assertEqual(result.status_code,302)
        self.repo.accept_parent_invite.assert_called_once_with(MEMBER,digest_code('b'*32))
        self.repo.provision_parent.assert_not_called()
        self.assertTrue(result.location.endswith('/admin'))

    def test_wrong_expired_invitation_never_falls_back_to_new_family(self):
        token=self.csrf('/sammytv/signin?role=parent')
        self.repo.accept_parent_invite.side_effect=ModerationDenied()
        result=self.client.post('/sammytv/signin',data=dict(csrf_token=token,role='parent',
            email='parent@example.test',password=PASSWORD,invitation='b'*32))
        self.assertEqual(result.status_code,401)
        self.repo.provision_parent.assert_not_called()

    def test_existing_invited_parent_can_return_without_invitation_or_allowlist(self):
        token=self.csrf('/sammytv/signin?role=parent')
        result=self.client.post('/sammytv/signin',data=dict(csrf_token=token,role='parent',
            email='invited@example.test',password=PASSWORD))
        self.assertEqual(result.status_code,302)
        self.repo.provision_parent.assert_not_called()
        self.repo.accept_parent_invite.assert_not_called()

    def test_parent_family_view_escapes_child_names_and_never_includes_password_hashes(self):
        self.parent()
        self.repo.children[0]['nickname']='<script>bad()</script>'
        response=self.client.get('/sammytv/admin/family')
        self.assertEqual(response.status_code,200)
        self.assertIn('&lt;script&gt;',response.text)
        self.assertNotIn('<script>bad()',response.text); self.assertNotIn(HASH,response.text)
        self.assertIn('private, no-store',response.headers['Cache-Control'])

    def test_parent_created_child_uses_current_family_and_hashed_password(self):
        self.parent()
        form=self.family_form()|dict(action='create',username='NEW_CHILD',nickname='Viewer',
                                    password=PASSWORD,password_confirm=PASSWORD,family_id=OTHER_FAMILY)
        result=self.client.post('/sammytv/admin/family',data=form)
        self.assertEqual(result.status_code,303)
        viewer,action=self.repo.manage_child.call_args.args
        self.assertEqual(viewer['family_id'],FAMILY); self.assertEqual(action,'create')
        kwargs=self.repo.manage_child.call_args.kwargs
        self.assertEqual(kwargs['username'],'new_child'); self.assertTrue(password_matches(kwargs['password_hash'],PASSWORD))

    def test_parent_approves_recognised_request_with_versioned_child_token(self):
        self.parent()
        form=self.family_form()|dict(action='approve',child_confirmed='yes',child_id='forged')
        response=self.client.post('/sammytv/admin/family',data=form)
        self.assertEqual(response.status_code,303)
        self.assertEqual(self.repo.manage_child.call_args.kwargs['child_id'],CHILD)
        self.assertEqual(self.repo.manage_child.call_args.kwargs['expected_updated_at'],VERSION)

    def test_request_approval_needs_explicit_confirmation(self):
        self.parent()
        result=self.client.post('/sammytv/admin/family',data=self.family_form()|dict(action='approve'))
        self.assertEqual(result.status_code,400)
        self.repo.manage_child.assert_not_called()

    def test_tampered_other_family_or_expired_review_token_cannot_change_account(self):
        self.parent()
        form=self.family_form()|dict(action='disable')
        claims=jwt.decode(form['review_token'],SECRET,algorithms=['HS256'],audience='sammytv:child-review')
        for changes in (dict(family_id=OTHER_FAMILY),dict(parent_id=CHILD),dict(exp=1)):
            token=jwt.encode(claims|changes,SECRET,algorithm='HS256')
            result=self.client.post('/sammytv/admin/family',data=form|dict(review_token=token))
            self.assertEqual(result.status_code,409)
        self.repo.manage_child.assert_not_called()

    def test_concurrent_account_changes_return_review_conflict(self):
        self.parent()
        self.repo.manage_child.side_effect=ModerationConflict()
        result=self.client.post('/sammytv/admin/family',data=self.family_form()|dict(action='decline'))
        self.assertEqual(result.status_code,409)

    def test_password_reset_uses_new_hash_and_signed_current_child(self):
        self.parent()
        form=self.family_form()|dict(action='reset_password',password=PASSWORD,password_confirm=PASSWORD)
        self.assertEqual(self.client.post('/sammytv/admin/family',data=form).status_code,303)
        self.assertTrue(password_matches(self.repo.manage_child.call_args.kwargs['password_hash'],PASSWORD))
        self.assertEqual(self.repo.manage_child.call_args.kwargs['child_id'],CHILD)

    def test_pause_restore_decline_are_parent_only_and_csrf_protected(self):
        self.parent()
        form=self.family_form()
        for action in ('disable','enable','decline'):
            self.assertEqual(self.client.post('/sammytv/admin/family',data=form|dict(action=action)).status_code,303)
        self.assertEqual(self.client.post('/sammytv/admin/family',data=form|dict(action='disable',csrf_token='')).status_code,400)
        self.repo.member_row['role']='viewer'
        self.assertEqual(self.client.get('/sammytv/admin/family').status_code,403)
        self.assertEqual(self.client.post('/sammytv/admin/family',data=form|dict(action='disable')).status_code,403)

    def test_registration_codes_and_parent_invites_store_only_digests(self):
        self.parent()
        form=self.family_form()
        with patch('services.sammytv.family.secrets.token_urlsafe',return_value='c'*32):
            result=self.client.post('/sammytv/admin/family',data=form|dict(action='registration_code'))
            self.assertEqual(result.status_code,200); self.assertIn('c'*32,result.text)
            self.assertEqual(self.repo.create_registration_code.call_args.args[1],digest_code('c'*32))
            result=self.client.post('/sammytv/admin/family',data=form|dict(action='invite_parent',
                email='OTHER@example.test',parent_confirmed='yes'))
            self.assertEqual(result.status_code,200)
            self.assertEqual(self.repo.create_parent_invite.call_args.args[1:],(digest_code('c'*32),'other@example.test'))

    def test_parent_invitation_requires_permission_confirmation(self):
        self.parent()
        form=self.family_form()|dict(action='invite_parent',email='other@example.test')
        self.assertEqual(self.client.post('/sammytv/admin/family',data=form).status_code,400)
        self.repo.create_parent_invite.assert_not_called()

    def test_signout_returns_login_and_old_browser_session_is_removed(self):
        self.sign_in()
        token=self.csrf('/sammytv')
        self.assertEqual(self.client.post('/sammytv/logout',data={'csrf_token':token}).status_code,302)
        self.assertIsNone(self.client.get_cookie(COOKIE_NAME,path='/sammytv'))
        self.assertEqual(self.client.get('/sammytv/api/catalogue').status_code,401)

    def test_preview_cannot_create_or_read_family_accounts(self):
        with patch.dict(os.environ,SAMMYTV_MODE='preview'):
            for path in ('/sammytv/register','/sammytv/admin/family'):
                self.assertEqual(self.client.get(path).status_code,503)
                self.assertEqual(self.client.post(path).status_code,503)
