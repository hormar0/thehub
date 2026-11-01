#!/data/data/com.termux/files/usr/bin/bash
# Milestone Hub — Termux installer & launcher
# Usage: bash install.sh   (from the repo root, after cloning)
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing python3..."
  pkg update -y && pkg install -y python
fi

echo "Starting Milestone Hub on http://127.0.0.1:${PORT:-8080}"
cd app
python3 server.py &
SERVER_PID=$!
sleep 2

if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "http://127.0.0.1:${PORT:-8080}" || true
fi

echo "Server running (PID $SERVER_PID). Stop with: kill $SERVER_PID"
wait $SERVER_PID
