#!/usr/bin/env bash
# ============================================================
# The Hub — one-file installation pack for a NEW device
# (Android tablet / Termux, or any machine with git + python3)
#
# Usage on the new tablet:
#   1. Install Termux from F-Droid (NOT Play Store).
#   2. In Termux:
#        pkg update -y && pkg install -y git python curl
#   3. Save this file and run:
#        bash install-pack.sh
#      (or: curl -O <raw-url-of-this-file> && bash install-pack.sh)
#   4. Open http://127.0.0.1:8080 in the tablet browser.
#      Landscape recommended; layout adapts to tablet screens.
#
# Later updates on the same device:
#        bash ~/thehub/update.sh
# ============================================================
set -e

REPO="https://github.com/hormar0/thehub.git"
BRANCH="vibe/milestone-hub-c4557a"
DEST="$HOME/thehub"
PORT="${PORT:-8080}"

echo "==> Installing dependencies (python3, git) if missing"
if command -v pkg >/dev/null 2>&1; then
  pkg update -y >/dev/null 2>&1 || true
  command -v python3 >/dev/null 2>&1 || pkg install -y python
  command -v git >/dev/null 2>&1 || pkg install -y git
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 required"; exit 1; }

if [ -d "$DEST/.git" ]; then
  echo "==> Existing clone found at $DEST — updating instead"
  cd "$DEST"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
else
  echo "==> Cloning $REPO ($BRANCH) into $DEST"
  git clone "$REPO" "$DEST" --depth 1 --branch "$BRANCH"
  cd "$DEST"
fi

echo "==> Starting The Hub on http://127.0.0.1:$PORT"
pkill -f "python3 server.py" 2>/dev/null || true
sleep 1
cd "$DEST/app"
rm -f milestonehub.db   # fresh demo data on new install; delete this line to keep data
PORT=$PORT nohup python3 server.py > server.log 2>&1 &
sleep 2

echo ""
echo "==> The Hub is running at http://127.0.0.1:$PORT"
if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "http://127.0.0.1:$PORT" || true
else
  echo "    Open http://127.0.0.1:$PORT in your browser."
fi
echo "==> Stop:  pkill -f 'python3 server.py'"
echo "==> Update later:  bash ~/thehub/update.sh"
