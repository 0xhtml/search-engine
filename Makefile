SYSTEM_UWSGI=0
ifeq ($(SYSTEM_UWSGI), 0)
	UWSGI=env/bin/uwsgi
else
	UWSGI=uwsgi
endif

.PHONY: run build static

build: static env lid.176.bin

run: build
	$(UWSGI) --ini uwsgi.ini --http 127.0.0.1:5000

static: static/logo.png.gz static/style.css.gz

static/style.css: scss/*.scss
	sass -s compressed scss/style.scss:static/style.css

static/%.gz: static/%
	gzip -fk9 $<

env: requirements.txt
	touch -c env
	test -d env || python -m venv env
	env/bin/pip install -r requirements.txt
ifeq ($(SYSTEM_UWSGI), 0)
	env/bin/pip install git+https://github.com/unbit/uwsgi@uwsgi-2.0
endif

lid.176.bin:
	wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
