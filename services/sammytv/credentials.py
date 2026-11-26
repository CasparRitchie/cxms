"""Local credential validation and shared, database-backed authentication limits."""
import hashlib
import hmac
import os
import re
import secrets

from flask import abort, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .repository import CatalogueUnavailable

USERNAME = re.compile(r'[a-z0-9][a-z0-9_.-]{2,31}')
CODE = re.compile(r'[A-Za-z0-9_-]{24,64}')
HASH_METHOD = 'scrypt:32768:8:1'
# Used for non-existent/pending users too, to avoid a cheap username oracle.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32), method=HASH_METHOD)


def username(value):
    value = value.strip().lower()
    if not USERNAME.fullmatch(value):
        raise ValueError('Use a username of 3–32 letters, numbers, dots, underscores or hyphens, starting with a letter or number.')
    return value


def nickname(value):
    value = value.strip()
    if not 1 <= len(value) <= 40 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Choose a display name of 1–40 characters. A nickname is fine.')
    return value


def password_hash(value):
    if not 10 <= len(value) <= 128:
        raise ValueError('Use a password of 10–128 characters. A few memorable words work well.')
    return generate_password_hash(value, method=HASH_METHOD)


def password_matches(stored, value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    if not isinstance(stored, str) or not stored.startswith(HASH_METHOD + '$') or len(stored) > 256:
        stored = DUMMY_HASH
        check_password_hash(stored, value)
        return False
    try:
        return check_password_hash(stored, value)
    except (ValueError, TypeError):
        return False


def digest_code(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(action, account='', *, limit=10, seconds=900):
    key = os.getenv('SAMMYTV_SESSION_SECRET', '')
    if len(key) < 32:
        raise CatalogueUnavailable('Session configuration incomplete.')
    # Heroku supplies the final X-Forwarded-For hop. Ignore earlier,
    # caller-controllable entries. Local requests use remote_addr.
    forwarded = request.headers.get('X-Forwarded-For', '')
    remote = forwarded.split(',')[-1].strip() if forwarded else (request.remote_addr or 'unknown')
    buckets = [(f'ip:{action}:{remote}', 50, seconds)]
    if account:
        buckets.append((f'account:{action}:{account}', limit, seconds))
    for value, maximum, window in buckets:
        bucket = hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
        if not g.sammytv_repository.auth_limit(bucket, maximum, window):
            abort(429, description='Too many attempts. Please wait a while before trying again.')
