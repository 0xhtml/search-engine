"""Module containing utils to work with human language."""

import fasttext

_MODEL = None


def detect_lang(text: str) -> str:
    """Detect language of given text, returning ISO language code."""
    global _MODEL

    if not _MODEL:
        _MODEL = fasttext.load_model("lid.176.bin")

    return _MODEL.predict(text)[0][0].removeprefix("__label__")
