FROM ubuntu:latest

ENV DEBIAN_FRONTEND noninteractive

ENV LANG=ja_JP.UTF-8
#ENV LC_ALL=ja_JP.UTF-8
#ENV LC_CTYPE=ja_JP.UTF-8

RUN apt-get update \
    && apt-get install -y git \
    && apt install -y python3 python3-dev python3-venv python-is-python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt-get/lists/*

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
#     && rm -rf /var/lib/apt-get/lists/* \
#     && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
#     && chmod 0440 /etc/sudoers.d/$USERNAME

# change user. Exec as vscode after this directive.
USER vscode

COPY requirements.txt .
RUN python3 -m venv $HOME/venv && \
    $HOME/venv/bin/pip install --upgrade pip && \
    $HOME/venv/bin/pip install --no-cache-dir -r requirements.txt

# activate venv for Pylance
RUN echo 'if [ -f "$HOME/venv/bin/activate" ] && [ -z "$VIRTUAL_ENV" ]; then' >> /home/vscode/.bashrc && \
    echo '    . "$HOME/venv/bin/activate"' >> /home/vscode/.bashrc && \
    echo 'fi' >> /home/vscode/.bashrc

# $HOME is not expand in ENV
ENV PATH="/home/vscode/venv/bin:$PATH"
