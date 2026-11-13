#!/bin/bash
# 在 Finder 裡雙擊就能開啟圖形介面
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "第一次使用，正在安裝需要的套件…"
  ./setup.sh || { echo "安裝失敗，按 Enter 關閉"; read; exit 1; }
fi
./niz68 gui
