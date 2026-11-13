#!/bin/bash
# 建立獨立的 Python 環境並安裝 hidapi（只需要跑一次）
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade hidapi
echo "安裝完成。接著執行: ./niz68 list"
