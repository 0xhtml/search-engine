FROM python:3.13 AS build-searxng

COPY searxng .

RUN ./manage py.build


FROM alpine:3.21.0 AS build-sass

RUN apk add --no-cache sassc

COPY scss .

RUN sassc -t compressed style.scss style.css


FROM python:3.13 AS build

COPY requirements.txt .
COPY --from=build-searxng dist/searxng-*-py3-none-any.whl .
RUN pip install -r requirements.txt searxng-*-py3-none-any.whl
RUN rm requirements.txt searxng-*-py3-none-any.whl

COPY locales locales
COPY searchengine searchengine
COPY static static
COPY --from=build-sass style.css static/style.css
COPY templates templates

RUN wget https://unpkg.com/htmx.org@2.0.2/dist/htmx.min.js -O static/htmx.min.js
RUN (wget -O- https://raw.githubusercontent.com/rimu/no-qanon/master/domains.txt && wget -O- https://raw.githubusercontent.com/quenhus/uBlock-Origin-dev-filter/main/dist/other_format/domains/global.txt) > domains.txt || (rm domains.txt && false)
RUN pybabel compile -d locales

EXPOSE 80
CMD ["uvicorn", "searchengine:app", "--host", "0.0.0.0", "--port", "80"]


FROM search-engine AS test

COPY dev-requirements.txt .
RUN pip install -r dev-requirements.txt
RUN rm dev-requirements.txt

COPY tests tests

CMD ["python", "-m", "pytest", "tests"]
