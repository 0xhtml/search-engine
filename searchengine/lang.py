"""Module containing utils to work with human language."""

from typing import Optional

import fasttext

_MODEL = None


def detect_lang(
    text: str,
    query_lang: Optional[str],
    default: Optional[str] = "en",
) -> str:
    """Detect language of given text, returning ISO language code."""
    global _MODEL

    if not _MODEL:
        _MODEL = fasttext.load_model("lid.176.bin")

    labels, _ = _MODEL.predict(" ".join(text.splitlines()), 10)

    supported_langs = {"en", "de"}
    if query_lang is not None:
        supported_langs.add(query_lang)

    langs = [
        lang
        for label in labels
        if (lang := label.removeprefix("__label__")) in supported_langs
    ]
    langs.append(default)

    return langs[0]
