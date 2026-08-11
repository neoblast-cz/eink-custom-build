#!/usr/bin/env bash
# Push local commits to GitHub, then pull + restart on the Pi.
set -e

PI_HOST="${PI_HOST:-192.168.1.52}"
PI_USER="${PI_USER:-neoblast}"

BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes present — commit or stash before deploying:"
    git status --short
    exit 1
fi

echo "=== Pushing $BRANCH to GitHub ==="
git push origin "$BRANCH"

echo "=== Deploying to $PI_USER@$PI_HOST ==="
ssh -t "$PI_USER@$PI_HOST" "cd ~/einkpi && git pull && sudo systemctl restart einkpi"

echo "=== Done. Web UI: http://$PI_HOST:8080/ ==="
