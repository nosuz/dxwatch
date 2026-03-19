# syntax=docker/dockerfile:1.4
FROM python:3-alpine

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ARG UV_CACHE_DIR=/opt/.cache/uv
RUN mkdir -p $UV_CACHE_DIR
# Disable development dependencies
ENV UV_NO_DEV=1
# specify `__pycache__` directory
ENV PYTHONPYCACHEPREFIX=/tmp/pycache

COPY pyproject.toml uv.lock ./
# set `--frozen` to `uv sync` on runtime
RUN --mount=type=cache,target=$UV_CACHE_DIR,sharing=locked \
    uv venv /opt/venv \
    && if [ -s uv.lock ]; then uv sync --frozen; fi

RUN chmod -R a+rX /opt/venv

COPY . .

ENTRYPOINT ["/opt/venv/bin/uvicorn","server:app","--host","0.0.0.0","--port","8000"]
