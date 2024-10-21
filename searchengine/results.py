"""Module containing the Result types."""

from typing import NamedTuple

from .url import Url


class WebResult(NamedTuple):
    """A web result consisting of title, url and text."""

    title: str
    url: Url
    text: str


class ImageResult(NamedTuple):
    """An image result consisting of title, url, text and src."""

    title: str
    url: Url
    text: str
    src: Url


class AnswerResult(NamedTuple):
    """An answer result consisting of answer and url."""

    answer: str
    url: Url


type Result = WebResult | ImageResult | AnswerResult
