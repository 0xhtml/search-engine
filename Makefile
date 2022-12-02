SYSTEM_UWSGI=0
ifeq ($(SYSTEM_UWSGI), 0)
	UWSGI=env/bin/uwsgi
else
	UWSGI=uwsgi
endif


.PHONY: build build_locales build_static run test


build: build_static build_locales env lid.176.bin

build_locales: $(patsubst %.po, %.mo, $(wildcard locales/*/LC_MESSAGES/*.po))

build_static: static/style.css.gz static/logo.png.gz


run: build
	$(UWSGI) --ini uwsgi.ini --http 127.0.0.1:5000


test: build
	env/bin/python -m pytest


%.mo: %.po
	msgfmt -o $@ $<

%.gz: %
	gzip -fk9 $<

static/style.css: scss/*.scss
	sass -s compressed scss/style.scss:static/style.css

env: requirements.txt
	touch -c env
	test -d env || python -m venv env
	env/bin/pip install -r requirements.txt
ifeq ($(SYSTEM_UWSGI), 0)
	env/bin/pip install git+https://github.com/unbit/uwsgi@uwsgi-2.0
endif

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
