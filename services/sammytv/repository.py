"""Server-only, read-only catalogue adapter. No dependency on other CXMS apps."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class CatalogueUnavailable(RuntimeError):
    """Safe to log by class name; never include upstream responses or credentials."""


class CatalogueRepository:
    def __init__(self):
        self.url = (os.getenv('SAMMYTV_SUPABASE_URL') or os.getenv('SUPABASE_URL', '')).rstrip('/')
        self.key = (os.getenv('SAMMYTV_SUPABASE_SERVICE_ROLE_KEY') or
                    os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SECRET_KEY', ''))

    def _request(self, resource, query=None, payload=None):
        if not self.key or urlparse(self.url).scheme != 'https' or not urlparse(self.url).netloc:
            raise CatalogueUnavailable('Catalogue configuration is incomplete.')
        if not resource.startswith(('sammytv_', 'rpc/sammytv_')):
            raise ValueError('Only SammyTV resources are permitted.')
        suffix = '?' + urlencode(query) if query else ''
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(self.url + '/rest/v1/' + resource + suffix, data=body,
                      headers={'apikey': self.key, 'Authorization': 'Bearer ' + self.key,
                               'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urlopen(req, timeout=8) as response:
                rows = json.load(response)
            if not isinstance(rows, list):
                raise CatalogueUnavailable('Unexpected catalogue response.')
            return rows
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise CatalogueUnavailable('Catalogue is temporarily unavailable.') from exc

    def member(self, family_id, member_id):
        rows = self._request('sammytv_members', {'select': 'id,family_id,role,active,session_version',
            'id': 'eq.' + member_id, 'family_id': 'eq.' + family_id, 'active': 'eq.true', 'limit': '1'})
        return rows[0] if rows else None

    def profile(self, family_id, profile_id):
        rows = self._request('sammytv_profiles', {'select': 'id,family_id,member_id,nickname,enabled',
            'id': 'eq.' + profile_id, 'family_id': 'eq.' + family_id, 'enabled': 'eq.true', 'limit': '1'})
        return rows[0] if rows else None

    def family(self, family_id):
        rows = self._request('sammytv_families', {'select': 'id,brand_name,enabled',
            'id': 'eq.' + family_id, 'enabled': 'eq.true', 'limit': '1'})
        return rows[0] if rows else None

    def categories(self, family_id):
        return self._request('sammytv_categories', {'select': 'id,name,slug,position',
            'family_id': 'eq.' + family_id, 'enabled': 'eq.true', 'order': 'position.asc,name.asc'})

    def videos(self, family_id, video_id=None, channel_id=None, category_id=None, query='', limit=48, offset=0):
        return self._request('rpc/sammytv_catalogue', payload={
            'p_family_id': family_id, 'p_video_id': video_id, 'p_channel_id': channel_id,
            'p_category_id': category_id, 'p_query': query, 'p_limit': limit, 'p_offset': offset})

    def channels(self, family_id):
        # The RPC only returns channels with at least one individually approved video.
        return self._request('rpc/sammytv_channels', payload={'p_family_id': family_id})

    def verify_parent(self, email, password):
        # Passwords and provider tokens are never persisted or returned to the browser.
        req = Request(self.url + '/auth/v1/token?grant_type=password',
            data=json.dumps({'email': email, 'password': password}).encode(),
            headers={'apikey': self.key, 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=8) as response:
                data = json.load(response)
            user = data.get('user', {})
            if not user.get('email_confirmed_at') or user.get('email', '').casefold() != email.casefold():
                return None
            return user.get('id')
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None

    def provision_parent(self, identity):
        rows = self._request('rpc/sammytv_provision_parent', payload={'p_identity': identity})
        return rows[0] if rows else None

    def create_pairing(self, family_id, member_id, digest):
        return self._request('rpc/sammytv_create_pairing', payload={
            'p_family': family_id, 'p_parent': member_id, 'p_digest': digest})

    def redeem_pairing(self, digest):
        rows = self._request('rpc/sammytv_redeem_pairing', payload={'p_digest': digest})
        return rows[0] if rows else None
