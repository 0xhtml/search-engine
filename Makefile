.PHONY: run clean setup

run: static/style.css uwsgi.ini
	env/bin/uwsgi --ini uwsgi.ini

static/style.css: scss/style.scss
	sass scss/style.scss:static/style.css

setup: requirements.txt
	python -m venv env
	env/bin/pip install -r requirements.txt

clean:
	rm -fr static/style.css* env
