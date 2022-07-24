"""Custom (meta) search engine."""

from flask import Flask, make_response, render_template, request

from . import engines, query, results

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


@application.route("/search")
def search():
    """Perform a search and return the search result page."""
    raw_query = request.args.get("q", None, str)

    if raw_query is None:
        return error("Wir haben keinen Suchbegriff empfangen können"), 404

    raw_query = raw_query.strip()

    if len(raw_query) == 0:
        return error("Der Suchbegriff ist leer")

    parsed_query = query.parse_query(raw_query)

    lang_engines = engines.LANG_MAP.get(
        parsed_query.lang, engines.LANG_MAP["*"]
    )

    sorted_results = results.order_results(
        [engine.search(parsed_query) for engine in lang_engines],
        parsed_query.lang,
    )

    return render_template("search.html", query=query, results=sorted_results)
