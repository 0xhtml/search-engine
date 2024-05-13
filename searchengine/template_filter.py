"""Module containing filter functions for the templates."""

import markupsafe

from .query import ParsedQuery


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    string = markupsafe.escape(string)

    for word in query.words:
        word = word.lower()
        word_length = len(word)

        start = 0

        while (start := string.lower().find(word, start)) > -1:
            bold = (
                markupsafe.Markup("<b>")
                + string[start : start + word_length]
                + markupsafe.Markup("</b>")
            )
            string = string[:start] + bold + string[start + word_length :]
            start += len(bold)

    return string


TEMPLATE_FILTER_MAP = {"highlight": _highlight}
