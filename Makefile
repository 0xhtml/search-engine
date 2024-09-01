.PHONY: build run test

SEARXNG:=searxng/dist/searxng-$(shell cd searxng && python -c 'from searx import version; print(version.VERSION_TAG)')-py3-none-any.whl
LOCALES:=$(patsubst %.po, %.mo, $(wildcard locales/*/LC_MESSAGES/*.po))

build: $(LOCALES) static/style.css env lid.176.bin

run: build
	env/bin/uvicorn searchengine:app --reload

test: env
	env/bin/python -m pytest

%.mo: %.po
	msgfmt -o $@ $<

static/style.css: scss/*.scss
	sass -s compressed --embed-source-map scss/style.scss:static/style.css

env: requirements.txt $(SEARXNG)
	(test -d env && touch env) || python -m venv env
	env/bin/pip install -r requirements.txt $(SEARXNG)

$(SEARXNG):
	cd searxng && ./manage py.build

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
