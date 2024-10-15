.PHONY: build run test

SEARXNG:=searxng/dist/searxng-$(shell cd searxng && python -c 'from searx import version; print(version.VERSION_TAG)')-py3-none-any.whl
LOCALES:=$(patsubst %.po, %.mo, $(wildcard locales/*/LC_MESSAGES/*.po))

build: $(LOCALES) static/style.css static/htmx.min.js env lid.176.bin domains.txt

run: build
	env/bin/uvicorn searchengine:app --reload

test: env
	env/bin/python -m pytest tests

%.mo: %.po
	msgfmt -o $@ $<

static/style.css: scss/*.scss
	sass -s compressed --embed-source-map scss/style.scss:static/style.css

static/htmx.min.js:
	wget https://unpkg.com/htmx.org@2.0.2/dist/$(@F) -O $@

env: requirements.txt $(SEARXNG)
	(test -d env && touch env) || python -m venv env
	env/bin/pip install -r requirements.txt $(SEARXNG)

$(SEARXNG):
	cd searxng && ./manage py.build

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin

domains.txt:
	(wget -O- https://raw.githubusercontent.com/rimu/no-qanon/master/domains.txt && wget -O- https://raw.githubusercontent.com/quenhus/uBlock-Origin-dev-filter/main/dist/other_format/domains/global.txt) > domains.txt || rm domains.txt
