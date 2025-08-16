"""Module containing common types."""

import traceback
from enum import Enum
from typing import NamedTuple, Optional


class SearchMode(Enum):
    """Search mode determining which type of results to return."""

    WEB = "web"
    IMAGES = "images"
    SCHOLAR = "scholar"

    @classmethod
    def from_searx_category(cls, categories: list[str]) -> "SearchMode":
        """Convert searx category to search mode."""
        if "general" in categories:
            return cls.WEB
        if "images" in categories:
            return cls.IMAGES
        if "science" in categories:
            return cls.SCHOLAR
        msg = f"Unknown searx category: {categories}"
        raise ValueError(msg)

    def __str__(self) -> str:
        """Return capitalized value."""
        return self.value.capitalize()


class Search(NamedTuple):
    """A search request."""

    words: tuple[str, ...]
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


def pretty_exc(exc: BaseException) -> str:
    """Return a pretty string for an exception."""
    return traceback.format_exception_only(exc)[0]
