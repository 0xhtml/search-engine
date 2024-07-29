"""Module containing the Result types."""

from typing import NamedTuple, Optional

import httpx


class WebResult(NamedTuple):
    """A web result consisting of title, url and text."""

    title: str
    url: httpx.URL
    text: Optional[str]

class ImageResult(NamedTuple):
    """An image result consisting of title, url, text and src."""

    title: str
    url: httpx.URL
    text: Optional[str]
    src: httpx.URL


class AnswerResult(NamedTuple):
    """An answer result consisting of answer and url."""

    answer: str
    url: httpx.URL


Result = WebResult | ImageResult | AnswerResult
