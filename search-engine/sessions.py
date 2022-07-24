"""Module to store session data of engines."""

import enum

import uwsgi

_CACHE_NAME = "sessions"


class Locks(enum.Enum):
    """Enum to manage ids of different locks."""

    GOOGLE = enum.auto()


def lock(num: Locks):
    """Lock a lock to use session data."""
    uwsgi.lock(num.value)


def unlock(num: Locks):
    """Unlock a lock."""
    uwsgi.unlock(num.value)


def get(key: bytes) -> bytes:
    """Get."""
    return uwsgi.cache_get(key, _CACHE_NAME)


def set(key: bytes, value: bytes, expires: int):
    """Update."""
    uwsgi.cache_update(key, value, expires, _CACHE_NAME)


def has_expired(key: bytes) -> bool:
    """Check wether session data has expired."""
    return not uwsgi.cache_exists(key, _CACHE_NAME)
