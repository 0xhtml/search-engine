SEARXNG:=searxng/dist/searxng-$(shell cd searxng && python -c 'from searx import version; print(version.VERSION_TAG)')-py3-none-any.whl
LOCALES:=$(patsubst %.po,%.mo,$(wildcard locales/*/LC_MESSAGES/*.po))

.PHONY: build
build: $(LOCALES) static/style.css static/htmx.min.js env domains.txt

.PHONY: run
run: build
	env/bin/uvicorn searchengine:app --reload

.PHONY: test
test: env/dev build
	env/bin/python -m pytest tests

.PHONY: extract-locales
extract-locales: env
	env/bin/pybabel extract -F locales/babel.cfg -o locales/messages.pot .

.PHONY: update-locales
update-locales: env
	env/bin/pybabel update -d locales -i locales/messages.pot

$(LOCALES)&: $(patsubst %.mo,%.po,$(LOCALES)) | env
	env/bin/pybabel compile -d locales

static/%.css: scss/%.scss scss/*.scss
	sass -s compressed $<:$@

static/htmx.min.js:
	wget https://unpkg.com/htmx.org@2.0.2/dist/htmx.min.js -O static/htmx.min.js

env: requirements.txt $(SEARXNG)
	rm -rf env
	python -m venv env || (rm -r env && false)
	env/bin/pip install $(patsubst %.txt,-r %.txt,$^) || (rm -r env && false)

env/dev: dev-requirements.txt env
	env/bin/pip install -r dev-requirements.txt || (rm -r env && false)
	touch env/dev

$(SEARXNG):
	cd searxng && ./manage py.build

domains.txt:
	(wget -O- https://raw.githubusercontent.com/rimu/no-qanon/master/domains.txt && wget -O- https://raw.githubusercontent.com/quenhus/uBlock-Origin-dev-filter/main/dist/other_format/domains/global.txt) > domains.txt || (rm domains.txt && false)
