# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt

FROM ${PYTHON_IMAGE}
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY app /srv/app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    APP_WORKERS=2 \
    DB_POOL_PER_WORKER=10
WORKDIR /srv
USER 10001
EXPOSE 8080
STOPSIGNAL SIGTERM
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${APP_WORKERS} --loop uvloop --http httptools --no-access-log --log-level error --backlog 2048 --timeout-keep-alive 60 --timeout-graceful-shutdown 10"]
