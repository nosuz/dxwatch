# syntax=docker/dockerfile:1.4
FROM ubuntu:latest

ENV LANG=ja_JP.UTF-8
#ENV LC_ALL=ja_JP.UTF-8
#ENV LC_CTYPE=ja_JP.UTF-8

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

# RUN apt-get update \
#     && apt-get install -y sudo \
#     && apt-get clean \
#     && rm -rf /var/lib/apt-get/lists/* \
#     && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
#     && chmod 0440 /etc/sudoers.d/$USERNAME

# install packages
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    # ssh is required to handle GitHub in the container
    git ssh \
    python3 python3-dev python3-venv python-is-python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt-get/lists/*

# change user. Exec as vscode after this directive.
USER vscode

COPY requirements.txt .
RUN python3 -m venv $HOME/venv && \
    $HOME/venv/bin/pip install --upgrade pip && \
    $HOME/venv/bin/pip install --no-cache-dir -r requirements.txt

# activate venv for Pylance
RUN cat <<EOF >> /home/vscode/.bashrc

if [ -f "$HOME/venv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then
    . "$HOME/venv/bin/activate"
fi
EOF

# $HOME is not expand in ENV
ENV PATH="/home/vscode/venv/bin:$PATH"
