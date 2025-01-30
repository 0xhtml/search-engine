FROM alpine:3.21

RUN apk add --no-cache py3-pip

ARG SEARXNG
COPY requirements.txt .
COPY $SEARXNG .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt ${SEARXNG##*/}
RUN rm requirements.txt ${SEARXNG##*/}

COPY domains.txt .
COPY locales locales
COPY searchengine searchengine
COPY static static
COPY templates templates

EXPOSE 80
CMD ["uvicorn", "searchengine:app", "--host", "0.0.0.0", "--port", "80"]
