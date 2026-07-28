from datetime import datetime, timezone


def lock_timeout_seconds():
    """Compatibility value for older clients and the existing RPC signature.

    Locks no longer expire automatically. A lock is released explicitly when
    editing ends, or by a Supervisor force-unlock after an abandoned session.
    """
    return 0


def utc_now():
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def lock_is_active(lock, now=None):
    return bool(lock and lock.get("lock_user_id") and lock.get("lock_token"))


def public_lock(lock, now=None):
    if not lock_is_active(lock, now=now):
        return None
    return {
        "owner_id": lock.get("lock_user_id"),
        "owner_name": lock.get("lock_user_name") or "Another user",
        "token": lock.get("lock_token"),
        "version": int(lock.get("lock_version") or 0),
        "acquired_at": lock.get("lock_acquired_at"),
        "last_active_at": lock.get("lock_last_active_at"),
        "expires_at": None,
        "timeout_seconds": None,
    }
