"""SHA hash function for proxy URLs."""

import hashlib
import secrets

from .url import Url

_SECRET = secrets.token_bytes(32)


def gen_sha(url: Url) -> str:
    """Return a SHA-256 hash of the URL with a secret key."""
    return hashlib.sha256(_SECRET + str(url).encode()).hexdigest()
