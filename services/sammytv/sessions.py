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


def form_page(kind, message='', code=''):
    token = csrf()
    response = make_response(render_template('sammytv/signin.html', kind=kind,
        csrf_token=token, message=message, code=code))
    response.set_cookie(CSRF_COOKIE, token, secure=True, httponly=True,
                        samesite='Strict', path='/sammytv', max_age=3600)
    return response


def issue_session(record):
    # Records come from server-only RPCs; subsequent requests revalidate membership.
    now = int(time.time())
    token = jwt.encode(dict(sub=record['member_id'], family_id=record['family_id'],
        profile_id=record['profile_id'], session_version=record['session_version'],
        iss=ISSUER, aud=AUDIENCE, iat=now, exp=now + 86400), secret(), algorithm='HS256')
    response = redirect(url_for('sammytv.page'))
    response.set_cookie(COOKIE_NAME, token, secure=True, httponly=True,
                        samesite='Strict', path='/sammytv', max_age=86400)
    return response


def register(blueprint):
    @blueprint.route('/signin', methods=['GET', 'POST'])
    def signin():
        if request.method == 'GET':
            return form_page('signin')
        check_csrf()
        email = request.form.get('email', '').strip().casefold()
        allowed = {x.strip().casefold() for x in os.getenv('SAMMYTV_PARENT_EMAILS', '').split(',') if x.strip()}
        password = request.form.get('password', '')
        if email not in allowed or not password or len(password) > 1024:
            return form_page('signin', 'Sign-in could not be completed.'), 401
        repo = g.sammytv_repository
        identity = repo.verify_parent(email, password)
        if not identity:
            return form_page('signin', 'Sign-in could not be completed.'), 401
        record = repo.provision_parent(identity)
        if not record:
            raise AccessDenied('Sign-in could not be completed.')
        return issue_session(record)

    @blueprint.route('/pair', methods=['GET', 'POST'])
    def pair():
        if request.method == 'GET':
            return form_page('pair')
        check_csrf()
        code = request.form.get('code', '').strip()
        if len(code) != 32:
            return form_page('pair', 'This code is invalid or has expired.'), 401
        record = g.sammytv_repository.redeem_pairing(hashlib.sha256(code.encode()).hexdigest())
        if not record:
            return form_page('pair', 'This code is invalid or has expired.'), 401
        return issue_session(record)

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
        return response
