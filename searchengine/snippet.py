"""Module to get snippets for search results."""

from typing import NamedTuple, Optional, Self

import curl_cffi
import lxml.html
import pygments
import pygments.formatters
import pygments.lexers

from .url import URL


class Snippet(NamedTuple):
    """A snippet for a search result."""

    text: str
    lang: str

    @classmethod
    async def load(cls, session: curl_cffi.AsyncSession, url: URL) -> Optional[Self]:
        """Get a snippet for a search result."""
        if url.host != "stackoverflow.com":
            return None

        response = await session.get(url.geturl())

        if not response.ok:
            return None

        dom = lxml.html.fromstring(response.content)

        fallback_lang = None
        if (elem := dom.find(".//div[@id='js-codeblock-lang']")) is not None:
            assert isinstance(elem, lxml.html.HtmlElement)
            if (text := elem.text_content()).startswith("lang-"):
                fallback_lang = text

        for elem in dom.findall(".//div[@itemprop='acceptedAnswer']//pre/code"):
            assert isinstance(elem, lxml.html.HtmlElement)
            langs = [cls for cls in elem.getparent().classes if cls.startswith("lang-")]
            if (lang := langs[0] if langs else fallback_lang) is not None:
                return cls(elem.text_content(), lang.removeprefix("lang-"))

        return None

    def render(self) -> str:
        """Render the snippet."""
        try:
            lexer = pygments.lexers.get_lexer_by_name(self.lang)
        except pygments.util.ClassNotFound:
            print(f"Unknown language: {self.lang}")
            return ""

        return pygments.highlight(self.text, lexer, pygments.formatters.HtmlFormatter())
