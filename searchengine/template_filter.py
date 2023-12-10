"""Module containing filter functions for the templates."""

import markupsafe

from .query import ParsedQuery


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    string = markupsafe.escape(string)

    for query_part in query.query_parts:
        lower_query_part = query_part.lower()
        query_part_length = len(query_part)

        start = 0

        while (start := string.lower().find(lower_query_part, start)) > -1:
            bold = (
                markupsafe.Markup("<b>")
                + string[start : start + query_part_length]
                + markupsafe.Markup("</b>")
            )
            string = string[:start] + bold + string[start + query_part_length :]
            start += len(bold)

    return string


TEMPLATE_FILTER_MAP = {"highlight": _highlight}
