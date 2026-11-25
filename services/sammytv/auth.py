"""Dedicated app sessions. Sports workspace cookies and roles are never accepted."""
import os
from uuid import UUID

import jwt
from flask import g, request

COOKIE_NAME = 'sammytv_session'
ISSUER = 'cxms:sammytv'
AUDIENCE = 'sammytv'


class AccessDenied(RuntimeError):
    status_code = 401


class ParentAccessDenied(AccessDenied):
    status_code = 403


def uuid_string(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise AccessDenied('Invalid identifier.') from None


def current_viewer(repository):
    """Validate cryptographic identity AND current database membership every request."""
    if hasattr(g, 'sammytv_viewer'):
        return g.sammytv_viewer
    secret = os.getenv('SAMMYTV_SESSION_SECRET', '')
    token = request.cookies.get(COOKIE_NAME, '')
    if len(secret) < 32 or not token or len(token) > 4096:
        raise AccessDenied('Sign in to open your collection.')
    try:
        claims = jwt.decode(token, secret, algorithms=['HS256'], issuer=ISSUER, audience=AUDIENCE,
            options={'require': ['sub', 'family_id', 'profile_id', 'iat', 'exp', 'session_version']})
        member_id = uuid_string(claims['sub'])
        family_id = uuid_string(claims['family_id'])
        profile_id = uuid_string(claims['profile_id'])
        if claims['exp'] - claims['iat'] > 86400:
            raise AccessDenied('Session lifetime is too long.')
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise AccessDenied('Sign in to open your collection.') from None
    member = repository.member(family_id, member_id)
    profile = repository.profile(family_id, profile_id)
    family = repository.family(family_id)
    if not member or not profile or not family:
        raise AccessDenied('This collection is unavailable.')
    if (member.get('id') != member_id or member.get('family_id') != family_id or
            profile.get('id') != profile_id or profile.get('family_id') != family_id or
            family.get('id') != family_id or not member.get('active') or
            not profile.get('enabled') or not family.get('enabled') or
            type(claims['session_version']) is not int or
            member.get('session_version') != claims['session_version'] or
            member.get('role') not in ('parent', 'viewer') or
            (member['role'] == 'viewer' and profile.get('member_id') != member_id)):
        raise AccessDenied('This collection is unavailable.')
    g.sammytv_viewer = {'member_id': member_id, 'family_id': family_id, 'profile_id': profile_id,
                       'role': member['role'], 'nickname': profile['nickname'],
                       'brand_name': family['brand_name']}
    return g.sammytv_viewer


def require_parent(viewer):
    if viewer['role'] != 'parent':
        raise ParentAccessDenied('Parent access is required.')
