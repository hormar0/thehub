#!/data/data/com.termux/files/usr/bin/bash
# Milestone Hub — one-command updater for Termux.
# Run from anywhere:  bash ~/thehub/update.sh
set -e

cd "$(dirname "$0")"

BRANCH="${1:-vibe/milestone-hub-c4557a}"

echo "==> Fetching latest from GitHub"
git fetch origin

echo "==> Switching to $BRANCH and pulling"
git checkout "$BRANCH"
git pull origin "$BRANCH"

echo "==> Restarting Milestone Hub"
pkill -f "python3 server.py" 2>/dev/null || true
sleep 1
bash install.sh
