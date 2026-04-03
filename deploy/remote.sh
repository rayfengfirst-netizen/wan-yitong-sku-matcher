#!/usr/bin/env bash
# 从本机一键发布到生产（见 README_DEPLOY.md「本机发布脚本」）
set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-root@8.218.58.28}"
REMOTE_DIR="${REMOTE_DIR:-/opt/wan-yitong-sku-matcher}"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25)
if [[ -n "${DEPLOY_SSH_IDENTITY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_SSH_IDENTITY" -o IdentitiesOnly=yes)
fi

RDIR=$(printf %q "$REMOTE_DIR")
exec ssh "${SSH_OPTS[@]}" "$DEPLOY_HOST" \
  "set -euo pipefail; cd $RDIR && git pull && source .venv/bin/activate && pip install -q -r requirements.txt && systemctl restart wan-yitong-sku-matcher && sleep 2 && systemctl is-active wan-yitong-sku-matcher && curl -sS http://127.0.0.1:6578/health && echo && echo OK: published"
