"""Module containing custom URL type."""

import socket
from typing import NamedTuple, Optional, Self
from urllib.parse import parse_qs, quote, unquote

import regex
from rfc3986 import uri_reference


def _default_port(scheme: str) -> Optional[int]:
    try:
        return socket.getservbyname(scheme)
    except OSError:
        return None


_COMPARABLE_SCHEMES = {"https": "http"}
_PATH_REMOVE = regex.compile("/+(?:(?=/)|$)")


class URL(NamedTuple):
    """An URL."""

    scheme: str
    host: str
    path: str
    query: Optional[str]
    fragment: Optional[str]

    @classmethod
    def parse(cls, url: str) -> Self:
        """Parse URL string into URL object."""
        parsed = uri_reference(url).normalize()
        assert parsed.scheme
        assert parsed.userinfo is None
        assert parsed.host
        assert parsed.port is None or (
            (default_port := _default_port(parsed.scheme)) is not None
            and parsed.port == str(default_port)
        )
        return cls(
            parsed.scheme,
            parsed.host,
            quote(unquote(parsed.path or "")),
            parsed.query,
            parsed.fragment,
        )

    def geturl(self) -> str:
        """Return URL string."""
        result = f"{self.scheme}://{self.host}{self.path}"
        if self.query is not None:
            result += f"?{self.query}"
        if self.fragment is not None:
            result += f"#{self.fragment}"
        return result

    def _cmp_scheme(self) -> str:
        return _COMPARABLE_SCHEMES.get(self.scheme, self.scheme)

    def _cmp_host(self) -> str:
        host = self.host.removeprefix("www.")
        if host.endswith(".m.wikipedia.org"):
            return host.removesuffix(".m.wikipedia.org") + ".wikipedia.org"
        return host

    def _cmp_path(self) -> str:
        return _PATH_REMOVE.sub(
            "",
            (
                self.path.replace("%E2%80%93", "-")
                if self.host.endswith(".wikipedia.org")
                else self.path
            ),
        )

    def _cmp_query(self) -> dict[str, list[str]]:
        return parse_qs(self.query, keep_blank_values=True)

    def __eq__(self, other: object) -> bool:
        """Check if two URLs are equal."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return (
            self._cmp_scheme() == other._cmp_scheme()
            and self._cmp_host() == other._cmp_host()
            and self._cmp_path() == other._cmp_path()
            and self._cmp_query() == other._cmp_query()
        )
