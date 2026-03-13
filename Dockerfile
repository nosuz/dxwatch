# syntax=docker/dockerfile:1.4
FROM python:3-alpine

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ARG UV_CACHE_DIR=/tmp/uv.cache
RUN mkdir -p $UV_CACHE_DIR
# Disable development dependencies
ENV UV_NO_DEV=1
# specify `__pycache__` directory
ENV PYTHONPYCACHEPREFIX=/tmp/pycache

COPY pyproject.toml uv.lock ./
# set `--frozen` to `uv sync` on runtime
RUN --mount=type=cache,target=$UV_CACHE_DIR,sharing=locked \
    uv venv /home/vscode/venv \
    && if [ -s uv.lock ]; then uv sync --frozen; fi

COPY . .

ENTRYPOINT ["uv", "run", "uvicorn", "server:app", \
    "--host", "0.0.0.0", "--port", "8000"]
