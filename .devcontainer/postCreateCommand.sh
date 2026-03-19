#!/usr/bin/bash

set -eu

# install Rust

# チェック対象のディレクトリとマーカーファイル
MARKER_FILE="$HOME/.postCreateCommand-done"

# マーカーファイルがなければ初期化スクリプトを実行
if [ -f "$MARKER_FILE" ]; then
  exit 0
fi

# 初期化完了を示すマーカーファイルを作成
touch "$MARKER_FILE"

# mkdir -p /workspaces/.codex
# ln -sfn /workspaces/.codex ~/.codex

mkdir -p /workspaces/.claude
ln -sfn /workspaces/.claude ~/.claude
