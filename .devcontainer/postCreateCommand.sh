#!/usr/bin/bash

set -eu

# install Rust

# チェック対象のディレクトリとマーカーファイル
MARKER_FILE="$HOME/.postCreateCommand-done"

# マーカーファイルがなければ初期化スクリプトを実行
if [ -f "$MARKER_FILE" ]; then
  exit 0
fi

mkdir -p /workspaces/.codex
if [ -e "$HOME/.codex" ] && [ ! -L "$HOME/.codex" ] ; then
  mv "$HOME/.codex" "$HOME/.codex.backup.$(date +%Y%m%d%H%M%S)"
fi
ln -s /workspaces/.codex ~/.codex

mkdir -p /workspaces/.claude
if [ -e "$HOME/.claude" ] && [ ! -L "$HOME/.claude" ] ; then
  mv "$HOME/.claude" "$HOME/.claude.backup.$(date +%Y%m%d%H%M%S)"
fi
ln -s /workspaces/.claude ~/.claude

# 初期化完了を示すマーカーファイルを作成
touch "$MARKER_FILE"
