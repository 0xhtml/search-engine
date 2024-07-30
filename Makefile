.PHONY: build build_locales build_static run test


build: build_static build_locales env lid.176.bin

build_locales: $(patsubst %.po, %.mo, $(wildcard locales/*/LC_MESSAGES/*.po))

build_static: static/style.css.gz static/logo.png.gz


run: build
	env/bin/uvicorn searchengine:app --reload

test: build
	env/bin/python -m pytest


%.mo: %.po
	msgfmt -o $@ $<

%.gz: %
	gzip -fk9 $<

static/style.css: scss/*.scss
	sass -s compressed --embed-source-map scss/style.scss:$@

env: requirements.txt requirements-searx.txt
	touch -c env
	test -d env || python -m venv env
	env/bin/pip install setuptools pyyaml
	env/bin/pip install --no-build-isolation -r requirements-searx.txt
	env/bin/pip install -r requirements.txt

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/$@
