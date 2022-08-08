"""Module containing filter functions for the templates."""

import markupsafe

from .query import ParsedQuery


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    string = markupsafe.escape(string)

    for query_part in query.query_parts:
        lower_query_part = query_part.lower()
        query_part_length = len(query_part)

        start = -query_part_length

        while (
            start := string.lower().find(
                lower_query_part, start + query_part_length
            )
        ) > -1:
            if start > 0 and string[start - 1].isalnum():
                continue

            end = start + query_part_length

            if end < len(string) and string[end].isalnum():
                continue

            string = (
                string[:start]
                + markupsafe.Markup("<b>")
                + string[start:end]
                + markupsafe.Markup("</b>")
                + string[end:]
            )

            start += len("<b></b>")

    return string


TEMPLATE_FILTER_MAP = {"highlight": _highlight}
