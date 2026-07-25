from datetime import datetime, timedelta, timezone
import os


DEFAULT_TIMEOUT_SECONDS = 15 * 60


def lock_timeout_seconds():
    try:
        value = int(os.getenv("SPORTS_EDITORIAL_EDIT_LOCK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        value = DEFAULT_TIMEOUT_SECONDS
    return max(60, value)


def utc_now():
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def lock_is_active(lock, now=None):
    if not lock or not lock.get("lock_user_id") or not lock.get("lock_last_active_at"):
        return False
    return parse_timestamp(lock["lock_last_active_at"]) + timedelta(seconds=lock_timeout_seconds()) > (now or utc_now())


def public_lock(lock, now=None):
    if not lock_is_active(lock, now=now):
        return None
    last_active = parse_timestamp(lock["lock_last_active_at"])
    return {
        "owner_id": lock.get("lock_user_id"),
        "owner_name": lock.get("lock_user_name") or "Another user",
        "token": lock.get("lock_token"),
        "version": int(lock.get("lock_version") or 0),
        "acquired_at": lock.get("lock_acquired_at"),
        "last_active_at": lock.get("lock_last_active_at"),
        "expires_at": (last_active + timedelta(seconds=lock_timeout_seconds())).isoformat(),
        "timeout_seconds": lock_timeout_seconds(),
    }
