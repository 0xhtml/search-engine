FROM alpine:3.21 AS locales
RUN apk add --no-cache py3-babel
COPY locales locales
RUN pybabel compile -d locales

FROM alpine:3.21 AS domains
ADD https://raw.githubusercontent.com/rimu/no-qanon/master/domains.txt .
ADD https://raw.githubusercontent.com/quenhus/uBlock-Origin-dev-filter/main/dist/other_format/domains/global.txt .
RUN cat domains.txt global.txt | grep -v \# | sort -u > domains.txt

FROM alpine:3.21 AS searxng
RUN apk add --no-cache py3-pyaml py3-setuptools patch
ADD https://github.com/searxng/searxng.git#194f22220306b7949660492bdbc3e5418835f88f .
RUN --mount=source=searxng.patch,dst=searxng.patch patch -p1 < searxng.patch
RUN python setup.py bdist_wheel

FROM alpine:3.21 AS scss
RUN apk add --no-cache sassc
COPY scss scss
RUN sassc -t compressed scss/style.scss style.css

FROM python:3-alpine3.21
RUN --mount=type=cache,target=/root/.cache/pip --mount=source=requirements.txt,dst=requirements.txt --mount=from=searxng,source=dist/searxng-1.0.0-py3-none-any.whl,dst=searxng-1.0.0-py3-none-any.whl pip install -r requirements.txt searxng-1.0.0-py3-none-any.whl
COPY searchengine searchengine
COPY templates templates
COPY static static
COPY --from=domains domains.txt .
COPY --from=locales locales locales
COPY --from=scss style.css static/.
ADD https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js static/.
EXPOSE 80
CMD ["uvicorn", "searchengine:app", "--host", "0.0.0.0", "--port", "80"]
