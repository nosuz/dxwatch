# syntax=docker/dockerfile:1.4
FROM ubuntu:latest
# suppress clear apt cache
RUN rm /etc/apt/apt.conf.d/docker-clean

ENV LANG=ja_JP.UTF-8
ENV LC_ALL=ja_JP.UTF-8
ENV LC_CTYPE=ja_JP.UTF-8
ENV TZ=Asia/Tokyo

ARG USERNAME=vscode
ARG UID=$UID
ARG GID=$GID

# Remove user if already exist and create new user.
RUN set -eux; \
    if getent passwd "${UID}" > /dev/null; then \
    echo "UID ${UID} already exists. Deleting..."; \
    userdel -f $(getent passwd "${UID}" | cut -d: -f1) || true; \
    fi; \
    if getent group "${GID}" > /dev/null; then \
    echo "GID ${GID} already exists. Deleting..."; \
    groupdel $(getent group "${GID}" | cut -d: -f1) || true; \
    fi; \
    groupadd --gid "${GID}" "${USERNAME}"; \
    useradd --uid "${UID}" --gid "${GID}" -s /bin/bash -m "${USERNAME}"

# install packages
ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    apt-get update \
    && apt-get install --no-install-recommends -y \
    # ssh is required to handle GitHub in the container
    # git ssh \
    python3 python3-venv \
    # curl is required to install uv
    curl \
    # System tools
    locales tzdata \
    # Configure locale
    && locale-gen ja_JP.UTF-8 \
    && update-locale LANG=ja_JP.UTF-8 \
    # Configure timezone
    && ln -fs /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

WORKDIR /app

COPY . .

# change user. Exec as vscode after this directive.
USER vscode

# install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV UV_PROJECT_ENVIRONMENT=/home/vscode/venv
ARG UV_CACHE_DIR=/home/vscode/.cache/uv
RUN mkdir -p $UV_CACHE_DIR

# blank uv.lock is just place holder.
# remove this before adding the initial library.
COPY pyproject.toml uv.lock ./
# set `--frozen` to `uv sync` on runtime
RUN --mount=type=cache,target=$UV_CACHE_DIR,uid=$UID,gid=$UID,sharing=locked \
    /home/vscode/.local/bin/uv venv /home/vscode/venv \
    && if [ -s uv.lock ]; then /home/vscode/.local/bin/uv sync --frozen; fi

# activate venv
# RUN cat <<'EOF' >> /home/vscode/.bashrc

# export LANG=$LANG

# if [ -n "$UV_PROJECT_ENVIRONMENT" ] &&
#     [ -f "$UV_PROJECT_ENVIRONMENT/bin/activate" ] &&
#     [ -z "$VIRTUAL_ENV" ]; then
#     . "$UV_PROJECT_ENVIRONMENT/bin/activate"
# fi
# EOF

ENTRYPOINT ["/home/vscode/.local/bin/uv", "run"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
