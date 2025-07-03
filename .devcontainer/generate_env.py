#!/usr/bin/env python3

import os

# 実行中のユーザーの UID と GID を取得
uid = os.getuid()
gid = os.getgid()

# スクリプト自身のディレクトリに .env ファイルを作成
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

# ファイルに書き込み
with open(env_path, 'w') as f:
    f.write(f"UID={uid}\n")
    f.write(f"GID={gid}\n")

print(f".env file created at: {env_path}")
