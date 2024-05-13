"""SHA hash function for proxy URLs."""

import hashlib
import secrets
import time

_SECRET = secrets.token_bytes(32)


def gen_sha(url: str) -> str:
    """Return a SHA-256 hash of the URL with a secret key and a timestamp."""
    return hashlib.sha256(
        str(round(time.time() / 60)).encode() + _SECRET + url.encode()
    ).hexdigest()
