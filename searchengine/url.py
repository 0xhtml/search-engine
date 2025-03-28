"""Module containing custom URL type."""

import socket
from typing import NamedTuple, Optional, Self
from urllib.parse import urlparse, urlunparse


def _default_port(scheme: str) -> Optional[int]:
    try:
        return socket.getservbyname(scheme)
    except OSError:
        return None


_COMPARABLE_SCHEMES = {"https": "http"}


class URL(NamedTuple):
    """An URL."""

    scheme: str
    netloc: str
    path: str
    params: str
    query: str
    fragment: str

    @classmethod
    def parse(cls, url: str) -> Self:
        """Parse URL string into URL object."""
        parsed = urlparse(url)

        if parsed.port is not None and parsed.port == _default_port(parsed.scheme):
            netloc = parsed.netloc.removesuffix(f":{parsed.port}")
            parsed = parsed._replace(netloc=netloc)

        return cls(*parsed)

    @property
    def host(self) -> str:
        """Get netloc."""
        return self.netloc

    def geturl(self) -> str:
        """Return URL string."""
        return urlunparse(self)

    def _cmp_scheme(self) -> str:
        return _COMPARABLE_SCHEMES.get(self.scheme, self.scheme)

    def _cmp_netloc(self) -> str:
        return self.netloc.removeprefix("www.").replace(
            ".m.wikipedia.org", ".wikipedia.org"
        )

    def _cmp_path(self) -> str:
        return (
            self.path.replace("%E2%80%93", "-")
            if self.netloc.endswith(".wikipedia.org")
            else self.path
        )

    def __eq__(self, other: object) -> bool:
        """Check if two URLs are equal."""
        if not isinstance(other, self.__class__):
            return NotImplemented

        if self._cmp_scheme() != other._cmp_scheme():
            return False

        if self._cmp_netloc() != other._cmp_netloc():
            return False

        if self._cmp_path() != other._cmp_path():
            return False

        if self.params != other.params:
            return False

        return self.query == other.query
