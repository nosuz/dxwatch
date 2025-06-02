#!/bin/bash

# UID と GID を取得
UID_VAL=$(id -u)
GID_VAL=$(id -g)

# スクリプト自身のディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# .env ファイルのパス
ENV_FILE="$SCRIPT_DIR/.env"

# .env ファイルに書き込む
{
  echo "UID=$UID_VAL"
  echo "GID=$GID_VAL"
} > "$ENV_FILE"

echo ".env file created at: $ENV_FILE"
