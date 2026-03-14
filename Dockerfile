# syntax=docker/dockerfile:1.4
FROM ubuntu:latest
# suppress clear apt cache
RUN rm /etc/apt/apt.conf.d/docker-clean

ENV LANG=ja_JP.UTF-8
ENV LC_ALL=ja_JP.UTF-8
ENV LC_CTYPE=ja_JP.UTF-8
ENV TZ=Asia/Tokyo

# install packages
ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    apt-get update \
    && apt-get install --no-install-recommends -y \
    # ssh is required to handle GitHub in the container
    # git ssh \
    python3 ca-certificates \
    # System tools
    locales tzdata \
    # Configure locale
    && locale-gen ja_JP.UTF-8 \
    && update-locale LANG=ja_JP.UTF-8 \
    # Configure timezone
    && ln -fs /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

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

COPY . .

RUN chmod -R a+rX /opt/venv

ENTRYPOINT ["/opt/venv/bin/uvicorn","server:app","--host","0.0.0.0","--port","8000"]
