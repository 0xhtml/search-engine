.PHONY: run build

run: build
	env/bin/uwsgi --ini uwsgi.ini

build: search-engine/static/style.css env lid.176.bin

search-engine/static/style.css: scss/*.scss
	sass scss/style.scss:search-engine/static/style.css

env: requirements.txt
	python -m venv env
	env/bin/pip install -r requirements.txt

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
