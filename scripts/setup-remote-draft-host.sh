#!/usr/bin/env bash
set -euo pipefail

# Run once on the WeChat-whitelisted host (124.222.245.133).
# It only needs draft-day; daily generation still runs on 251.

REPO="${1:-/home/ubuntu/github/i-love-economics}"
REPO_URL="${REPO_URL:-git@github.com:minghigh/i-love-economics.git}"

if [[ ! -d "${REPO}/.git" ]]; then
  git clone "${REPO_URL}" "${REPO}"
fi

cd "${REPO}"
git pull --ff-only

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "created ${REPO}/.env — fill WECHAT_APPID and WECHAT_APPSECRET"
fi

docker compose build draft-day
echo "ready: docker compose run --rm draft-day data/runs/YYYY-MM-DD"
