"""Module containing common types."""

from enum import Enum
from typing import NamedTuple, Optional


class SearchMode(Enum):
    """Search mode determining which type of results to return."""

    WEB = "web"
    IMAGES = "images"
    SCHOLAR = "scholar"

    def searx_category(self) -> str:
        """Convert search mode to searx category."""
        if self == SearchMode.WEB:
            return "general"
        if self == SearchMode.IMAGES:
            return "images"
        if self == SearchMode.SCHOLAR:
            return "science"
        raise ValueError

    def __str__(self) -> str:
        """Return capitalized value."""
        return self.value.capitalize()


class Search(NamedTuple):
    """A search request."""

    words: list[str]
    lang: str
    site: Optional[str]
    mode: SearchMode
    page: int

    def query_string(self) -> str:
        """Convert query parts to query string."""
        query = ""

        for word in self.words:
            if " " in word:
                query += f'"{word}" '
            else:
                query += f"{word} "

        if self.site is not None:
            query += f"site:{self.site} "

        return query[:-1]
