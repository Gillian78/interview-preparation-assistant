#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  open "http://127.0.0.1:8765/"
  exit 0
fi

echo "正在启动 AI 面试模拟助手..."
python3 "$APP_DIR/app.py" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for i in {1..30}; do
  if curl -s --max-time 1 http://127.0.0.1:8765/ >/dev/null 2>&1; then
    open "http://127.0.0.1:8765/"
    echo "已打开面试助手。关闭此窗口将停止本地服务。"
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 1
done

echo "服务启动失败，请检查 Python 环境或端口 8765。"
read -n 1 -s -r -p "按任意键退出..."
