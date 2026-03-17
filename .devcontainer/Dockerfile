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
    git ssh \
    python3 ca-certificates \
    # System tools
    locales tzdata \
    # Configure locale
    && locale-gen ja_JP.UTF-8 \
    && update-locale LANG=ja_JP.UTF-8 \
    # Configure timezone
    && ln -fs /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

# install npm
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y \
    # curl is required to install npm
    curl \
    # Node.js
    nodejs npm \
    # # pdftotext
    # python3-dev poppler-utils libpoppler-cpp-dev \
    # # OCR
    # tesseract-ocr tesseract-ocr-eng poppler-utils ocrmypdf ghostscript \
    # Claude Code
    # build-essential \
    # gnupg2 \
    # less \
    # fzf \
    # zsh \
    # man-db \
    # unzip \
    # gh \
    # jq \
    # install n
    && npm install n -g \
    && n stable \
    && apt purge -y nodejs npm \
    && apt autoremove -y

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

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

RUN chmod -R a+rX /opt/venv \
    && find /opt/venv -type d -perm -u+w -exec chmod a+w {} +

# activate venv
RUN cat <<'EOF' >> /etc/bash.bashrc

export LANG=$LANG

if [ -n "$UV_PROJECT_ENVIRONMENT" ] &&
    [ -f "$UV_PROJECT_ENVIRONMENT/bin/activate" ] &&
    [ -z "$VIRTUAL_ENV" ]; then
    . "$UV_PROJECT_ENVIRONMENT/bin/activate"
fi
EOF

# # install Codex
# ARG CODEX_BUST=0
# RUN echo "CODEX_BUST=$CODEX_BUST" \
#     && npm i -g @openai/codex

# install Caude
# Claude code is installed under ~/.local
USER ubuntu
ARG CLAUDE_BUST=0
RUN echo "CLAUDE_BUST=$CLAUDE_BUST" \
    && curl -fsSL https://claude.ai/install.sh | bash
USER root
