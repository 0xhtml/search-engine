"""URL class that extends urllib.parse.ParseResult."""

import urllib.parse


class Url(urllib.parse.ParseResult):
    """URL class that extends urllib.parse.ParseResult."""

    @classmethod
    def parse(cls, url: str) -> "Url":
        """Parse the url and return a new instance of Url."""
        return cls(*urllib.parse.urlparse(url))

    @property
    def host(self) -> str:
        """Return the netloc."""
        return self.netloc

    def __str__(self) -> str:
        """Return the URL."""
        return self.geturl()
