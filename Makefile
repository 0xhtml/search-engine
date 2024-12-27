.PHONY: build
build:
	docker build --target build -t search-engine .

.PHONY: run
run: build
	docker run -tp 8000:80 search-engine

.PHONY: test
test:
	docker build --target test -t search-engine-test .
	docker run -t search-engine-test

.PHONY: extract-locales
extract-locales: env
	env/bin/pybabel extract -F locales/babel.cfg -o locales/messages.pot .

.PHONY: update-locales
update-locales: env
	env/bin/pybabel update -d locales -i locales/messages.pot
