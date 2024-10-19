"""Module containing utils to work with human language."""

import regex
import searx.utils


def detect_lang(text: str, languages: list[str]) -> str:
    """Detect language of given text, returning ISO language code."""
    model = searx.utils._get_fasttext_model()  # noqa: SLF001
    labels, _ = model.predict(" ".join(text.splitlines()), 176)

    langs = [
        lang
        for label in labels
        if (lang := label.removeprefix("__label__")) in languages
    ] + languages

    return langs[0]


def is_lang(text: str, expected_lang: str) -> float:
    """Check to which confidence score the given text matches the expected language."""
    model = searx.utils._get_fasttext_model()  # noqa: SLF001
    labels, scores = model.predict(" ".join(text.splitlines()), 176)

    if f"__label__{expected_lang}" in labels:
        return scores[labels.index(f"__label__{expected_lang}")]

    return 0.0


# RFC 4234
# ---
# Appendix B.1. Core Rules
# https://www.rfc-editor.org/rfc/rfc4234.html#appendix-B.1
# ---
# ALPHA = %x41-5A / %x61-7A  ; A-Z / a-z
_ALPHA = "[A-Za-z]"
# DIGIT = %x30-39  ; 0-9
_DIGIT = "[0-9]"
# HTAB = %x09  ; horizontal tab
_HTAB = r"\t"
# SP = %x20
_SP = " "

# RFC 4647
# ---
# Section 2.1. Basic Language Range
# https://www.rfc-editor.org/rfc/rfc4647.html#section-2.1
# ---
# alphanum = ALPHA / DIGIT
_alphanum = f"(?:{_ALPHA}|{_DIGIT})"
# language-range = (1*8ALPHA *("-" 1*8alphanum)) / "*"
_language_range = rf"(?:(?<lang>{_ALPHA}{{1,8}})(?:-{_alphanum}{{1,8}})*|\*)"

# RFC 9110
# ---
# Section 5.6.3. Whitespace
# https://httpwg.org/specs/rfc9110.html#rfc.section.5.6.3
# ---
# OWS = *( SP / HTAB )  ; optional whitespace
_OWS = f"[{_SP}{_HTAB}]*"
# ---
# Section 12.4.2. Quality Values
# https://httpwg.org/specs/rfc9110.html#rfc.section.12.4.2
# ---
# qvalue = ( "0" [ "." 0*3DIGIT ] ) / ( "1" [ "." 0*3("0") ] )
_qvalue = rf"(?:0(?:\.{_DIGIT}{{,3}})?|1(?:\.0{{,3}})?)"
# weight = OWS ";" OWS "q=" qvalue
_weight = f"(?:{_OWS};{_OWS}q={_qvalue})"
# ---
# Section 12.5.4. Accept-Language
# https://httpwg.org/specs/rfc9110.html#rfc.section.12.5.4
# Appendix A
# https://httpwg.org/specs/rfc9110.html#rfc.section.A
# ---
# Accept-Language = [ ( language-range [ weight ] ) *( OWS "," OWS (
#  language-range [ weight ] ) ) ]
_Accept_Language = regex.compile(
    f"(?:{_language_range}{_weight}?(?:{_OWS},{_OWS}{_language_range}{_weight}?)*)?"
)


def parse_accept_language(value: str) -> list[str]:
    """Parse an Accept-Language header returning the list of languages."""
    match = _Accept_Language.match(value)
    if match is None:
        return []
    return list(dict.fromkeys(match.captures("lang")))
