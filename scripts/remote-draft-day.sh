#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REMOTE_HOST="${REMOTE_DRAFT_HOST:-124.222.245.133}"
REMOTE_USER="${REMOTE_DRAFT_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DRAFT_DIR:-/home/ubuntu/github/i-love-economics}"

day="${1:-yesterday}"
if [[ "$day" == "yesterday" ]]; then
  run_dir="data/runs/$(TZ=Asia/Shanghai date -d yesterday +%Y-%m-%d)"
elif [[ "$day" == */* ]]; then
  run_dir="${day#./}"
else
  run_dir="data/runs/${day}"
fi

if [[ ! -d "${run_dir}/candidates" ]]; then
  echo "missing ${run_dir}/candidates" >&2
  exit 1
fi

remote_run="${REMOTE_DIR}/${run_dir}"
remote="${REMOTE_USER}@${REMOTE_HOST}"
draft_cmd="${REMOTE_DRAFT_CMD:-python3 -m economics_daily}"

echo "sync ${run_dir} -> ${remote}:${remote_run}"
ssh "${remote}" "mkdir -p ${remote_run}"
rsync -az "${run_dir}/" "${remote}:${remote_run}/"

echo "draft-day on ${REMOTE_HOST}"
ssh "${remote}" "cd ${REMOTE_DIR} && ${draft_cmd} draft-day ${run_dir}"

echo "sync wechat-draft.json back"
rsync -az \
  --include='*/' \
  --include='wechat-draft.json' \
  --exclude='*' \
  "${remote}:${remote_run}/candidates/" \
  "${run_dir}/candidates/"
