.PHONY: run build static

build: static env/bin/uwsgi lid.176.bin

run: build
	env/bin/uwsgi --ini uwsgi.ini

static: static/logo.png.gz static/style.css.gz

static/style.css: scss/*.scss
	sass -s compressed scss/style.scss:static/style.css

static/%.gz: static/%
	gzip -fk9 $<

env/bin/uwsgi: requirements.txt env
	env/bin/pip install -r requirements.txt

env:
	python -m venv env

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
