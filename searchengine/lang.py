"""Module containing utils to work with human language."""

import fasttext

_MODEL = None


def _model() -> fasttext.FastText:
    global _MODEL

    if not _MODEL:
        _MODEL = fasttext.load_model("lid.176.bin")

    return _MODEL


def detect_lang(text: str) -> str:
    """Detect language of given text, returning ISO language code."""
    labels, _ = _model().predict(" ".join(text.splitlines()), 176)

    langs = [
        lang
        for label in labels
        if (lang := label.removeprefix("__label__")) in {"en", "de"}
    ] + ["en"]

    return langs[0]


def is_lang(text: str, expected_lang: str) -> float:
    """Check to which confidence score the given text matches the expected language."""
    labels, scores = _model().predict(" ".join(text.splitlines()), 176)

    if f"__label__{expected_lang}" in labels:
        return scores[labels.index(f"__label__{expected_lang}")]

    return 0.0
