"""Module containing the Result type."""

from typing import NamedTuple, Optional

import httpx


class Result(NamedTuple):
    """Single result returned by a search."""

    @classmethod
    def from_dict(cls, result: dict[str, str]) -> "Result":
        """Convert a dict returned by searx into a result tuple."""
        return cls(
            result["title"],
            httpx.URL(result["url"]),
            result["content"] or None,
            result.get("img_src"),
        )

    title: str
    url: httpx.URL
    text: Optional[str]
    src: Optional[str]
