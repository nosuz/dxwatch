# syntax=docker/dockerfile:1.4
FROM ubuntu:latest
# suppress clear apt cache
RUN rm /etc/apt/apt.conf.d/docker-clean

ENV LANG=ja_JP.UTF-8
ENV LC_ALL=ja_JP.UTF-8
ENV LC_CTYPE=ja_JP.UTF-8
ENV TZ=Asia/Tokyo

ARG USERNAME=vscode
ARG UID=10000
ARG GID=$UID

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

# Enable sudo
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,sharing=locked,target=/var/lib/apt \
    apt-get update \
    && apt-get install --no-install-recommends -y \
    # ssh is required to handle GitHub in the container
    git ssh \
    python3 python3-dev python3-venv python-is-python3 \
    # System tools
    locales tzdata \
    # Configure locale
    && locale-gen ja_JP.UTF-8 \
    && update-locale LANG=ja_JP.UTF-8 \
    # Configure timezone
    && ln -fs /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

# change user. Exec as vscode after this directive.
USER vscode

COPY requirements.txt .
ARG PIP_CACHE_DIR=/home/vscode/.cache/pip
RUN mkdir -p $PIP_CACHE_DIR
RUN --mount=type=cache,target=/home/vscode/.cache/pip \
    sudo chown vscode:vscode /home/vscode/.cache/pip \
    && python3 -m venv $HOME/venv \
    && $HOME/venv/bin/pip install --upgrade pip \
    && $HOME/venv/bin/pip install -r requirements.txt

# activate venv for Pylance
RUN cat <<EOF >> /home/vscode/.bashrc

if [ -f "$HOME/venv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then
    . "$HOME/venv/bin/activate"
fi
EOF

# $HOME is not expand in ENV
ENV PATH="/home/vscode/venv/bin:$PATH"
