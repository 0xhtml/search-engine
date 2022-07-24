"""Custom (meta) search engine."""

from collections import defaultdict, namedtuple

import fasttext
from flask import Flask, make_response, render_template, request

import engines

Result = namedtuple("Result", ["title", "url"])
application = Flask(__name__)


def error(message: str):
    """Return error page."""
    return render_template("index.html", error_message=message)


@application.errorhandler(404)
def page_not_found(_):
    """Return 404 error page."""
    if "text/html" in request.headers.get("Accept", ""):
        return error("Die Seite wurde nicht gefunden"), 404

    response = make_response("404 Not Found", 404)
    response.headers["Content-Type"] = "text/plain"
    return response


@application.route("/")
def index():
    """Return the start page."""
    return render_template("index.html")


FASTTEXT_MODEL = fasttext.load_model("/tmp/lid.176.bin")


def _detect_lang(text: str) -> str:
    return FASTTEXT_MODEL.predict([text])[0][0][0].replace("__label__", "")


@application.route("/search")
def search():
    """Perform a search and return the search result page."""
    query = request.args.get("q", None, str)

    if query is None:
        return error("Wir haben keinen Suchbegriff empfangen können"), 404

    query = query.strip()

    if len(query) == 0:
        return error("Der Suchbegriff ist leer")

    lang = _detect_lang(query)
    lang_engines = engines.LANG_MAP.get(lang, engines.LANG_MAP["*"])

    results = [engine.search(query) for engine in lang_engines]
    max_result_count = max(len(engine_results) for engine_results in results)

    rated_results = defaultdict(lambda: 0)
    for engine_results in results:
        for i, result in enumerate(engine_results):
            rated_results[result] += max_result_count - i

    for result in rated_results.keys():
        if _detect_lang(result.title) == lang:
            rated_results[result] += 2

    sorted_results = sorted(
        rated_results, key=rated_results.get, reverse=True  # type: ignore
    )

    return render_template("search.html", query=query, results=sorted_results)
