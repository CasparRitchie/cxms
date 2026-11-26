"""Parent authentication and single-use viewer device pairing."""
import hashlib
import hmac
import os
import secrets
import time

import jwt
from flask import abort, g, make_response, redirect, render_template, request, url_for

from .auth import AUDIENCE, COOKIE_NAME, ISSUER, AccessDenied, current_viewer, require_parent
from .repository import CatalogueRepository, CatalogueUnavailable
from .credentials import CODE, digest_code, password_matches, throttle, username
from .repository import ModerationDenied, ModerationInvalid

CSRF_COOKIE = 'sammytv_csrf'


def secret():
    value = os.getenv('SAMMYTV_SESSION_SECRET', '')
    if len(value) < 32:
        raise CatalogueUnavailable('Session configuration is incomplete.')
    return value


def csrf():
    token = request.cookies.get(CSRF_COOKIE, '')
    try:
        jwt.decode(token, secret(), algorithms=['HS256'], audience='sammytv:csrf',
                   options={'require': ['exp', 'nonce']})
        return token
    except jwt.PyJWTError:
        return jwt.encode({'nonce': secrets.token_urlsafe(24), 'aud': 'sammytv:csrf',
                           'exp': int(time.time()) + 3600}, secret(), algorithm='HS256')


def check_csrf():
    cookie = request.cookies.get(CSRF_COOKIE, '')
    if not cookie or not hmac.compare_digest(cookie, request.form.get('csrf_token', '')):
        abort(400)
    try:
        jwt.decode(cookie, secret(), algorithms=['HS256'], audience='sammytv:csrf',
                   options={'require': ['exp', 'nonce']})
    except jwt.PyJWTError:
        abort(400)


def form_page(kind, message='', code='', **context):
    token = csrf()
    response = make_response(render_template('sammytv/signin.html', kind=kind,
        csrf_token=token, message=message, code=code, **context))
    response.set_cookie(CSRF_COOKIE, token, secure=True, httponly=True,
                        samesite='Strict', path='/sammytv', max_age=3600)
    return response


def issue_session(record, *, parent=False):
    # Records come from server-only RPCs; subsequent requests revalidate membership.
    now = int(time.time())
    token = jwt.encode(dict(sub=record['member_id'], family_id=record['family_id'],
        profile_id=record['profile_id'], session_version=record['session_version'],
        iss=ISSUER, aud=AUDIENCE, iat=now, exp=now + 86400), secret(), algorithm='HS256')
    response = redirect(url_for('sammytv.admin') if parent else '/sammytv')
    response.set_cookie(COOKIE_NAME, token, secure=True, httponly=True,
                        samesite='Strict', path='/sammytv', max_age=86400)
    response.delete_cookie(COOKIE_NAME,path='/',secure=True,httponly=True,samesite='Strict')
    return response


def register(blueprint):
    @blueprint.route('/signin', methods=['GET', 'POST'])
    def signin():
        if request.method == 'GET':
            try:
                current_viewer(g.sammytv_repository)
                return redirect('/sammytv')
            except AccessDenied:
                pass
            role = request.args.get('role', 'child')
            if role not in ('child','parent'):
                abort(400)
            return form_page('signin', role=role)
        check_csrf()
        role = request.form.get('role', 'parent')
        repo = g.sammytv_repository
        if role == 'child':
            raw_username = request.form.get('username', '')
            throttle('child-signin', raw_username.strip().lower()[:128])
            try:
                login = username(raw_username)
            except ValueError:
                return form_page('signin', 'Check your username and password, or ask your parent for help.', role='child'), 401
            credential = repo.child_credentials(login)
            password = request.form.get('password', '')
            stored = credential.get('password_hash') if credential else None
            if password_matches(stored, password) and credential:
                record = repo.child_session(credential['child_id'], stored)
                if record:
                    return issue_session(record)
            return form_page('signin', 'Check your username and password, or ask your parent for help.', role='child'), 401
        if role != 'parent':
            abort(400)
        email = request.form.get('email', '').strip().casefold()
        throttle('parent-signin', email[:254])
        allowed = {x.strip().casefold() for x in os.getenv('SAMMYTV_PARENT_EMAILS', '').split(',') if x.strip()}
        password = request.form.get('password', '')
        invitation = request.form.get('invitation', '').strip()
        if not email or len(email)>254 or not password or len(password)>1024 or (invitation and not CODE.fullmatch(invitation)):
            return form_page('signin', 'Sign-in could not be completed.', role='parent'), 401
        identity = repo.verify_parent(email, password)
        if not identity:
            return form_page('signin', 'Sign-in could not be completed.', role='parent'), 401
        try:
            if invitation:
                record = repo.accept_parent_invite(identity, digest_code(invitation))
            else:
                record = repo.existing_parent(identity)
                if not record and email in allowed:
                    record = repo.provision_parent(identity)
        except (ModerationDenied, ModerationInvalid):
            record = None
        if not record:
            return form_page('signin', 'Sign-in could not be completed. Check your parent account and invitation, if you have one.', role='parent'), 401
        return issue_session(record, parent=True)

    @blueprint.route('/pair', methods=['GET', 'POST'])
    def pair():
        if request.method == 'GET':
            return form_page('pair')
        check_csrf()
        code = request.form.get('code', '').strip()
        throttle('pair', digest_code(code[:128]))
        if len(code) != 32:
            return form_page('pair', 'This code is invalid or has expired.'), 401
        record = g.sammytv_repository.redeem_pairing(hashlib.sha256(code.encode()).hexdigest())
        if not record:
            return form_page('pair', 'This code is invalid or has expired.'), 401
        return issue_session(record)

    @blueprint.route('/register', methods=['GET','POST'])
    def child_register():
        if request.method == 'GET':
            return form_page('register')
        check_csrf()
        code = request.form.get('family_code', '').strip()
        throttle('child-register', digest_code(code[:128]), limit=5, seconds=3600)
        try:
            if not CODE.fullmatch(code):
                raise ValueError('Ask your parent for a current family code.')
            from .credentials import nickname, password_hash
            login = username(request.form.get('username',''))
            display = nickname(request.form.get('nickname',''))
            hashed = password_hash(request.form.get('password',''))
            if request.form.get('password') != request.form.get('password_confirm'):
                raise ValueError('The passwords do not match.')
            requested = g.sammytv_repository.request_child(digest_code(code), login, display, hashed)
            if not requested:
                raise ValueError('The request could not be sent. Check your family code or ask your parent to create your login.')
        except ValueError as exc:
            return form_page('register', str(exc)), 400
        except (ModerationInvalid, ModerationDenied):
            return form_page('register', 'The request could not be sent. Try another username or ask your parent for help.'), 400
        return form_page('requested')

    @blueprint.route('/devices', methods=['GET', 'POST'])
    def devices():
        require_parent(g.sammytv_viewer)
        if request.method == 'GET':
            return form_page('devices')
        check_csrf()
        code = secrets.token_hex(16)
        viewer = g.sammytv_viewer
        g.sammytv_repository.create_pairing(viewer['family_id'], viewer['member_id'],
                                            hashlib.sha256(code.encode()).hexdigest())
        return form_page('devices', 'Use this code within ten minutes on the viewer device.', code)

    @blueprint.post('/logout')
    def logout():
        check_csrf()
        response = redirect(url_for('sammytv.signin'))
        response.delete_cookie(COOKIE_NAME, path='/sammytv', secure=True, httponly=True, samesite='Strict')
        response.delete_cookie(COOKIE_NAME, path='/', secure=True, httponly=True, samesite='Strict')
        return response
