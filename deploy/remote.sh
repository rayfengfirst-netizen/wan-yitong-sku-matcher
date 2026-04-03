#!/usr/bin/env bash
# 从本机一键发布到生产（见 README_DEPLOY.md「本机发布脚本」）
#
# 私钥若设置了 passphrase：须先让 ssh-agent 能用到密钥，否则在非交互环境会 Permission denied。
#   ssh-add ~/.ssh/id_ed25519
# 或 macOS 写入钥匙串后开机自动加载：
#   ssh-add --apple-use-keychain ~/.ssh/id_ed25519
#
# 需要「失败即退出、不要卡住等密码」时（如部分 CI）：  SSH_BATCH_MODE=yes ./deploy/remote.sh
set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-root@8.218.58.28}"
REMOTE_DIR="${REMOTE_DIR:-/opt/wan-yitong-sku-matcher}"

SSH_OPTS=(-o ConnectTimeout=25)
if [[ "${SSH_BATCH_MODE:-}" == "yes" ]]; then
  SSH_OPTS+=(-o BatchMode=yes)
fi
if [[ -n "${DEPLOY_SSH_IDENTITY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_SSH_IDENTITY" -o IdentitiesOnly=yes)
fi

RDIR=$(printf %q "$REMOTE_DIR")
exec ssh "${SSH_OPTS[@]}" "$DEPLOY_HOST" \
  "set -euo pipefail; cd $RDIR && git pull && source .venv/bin/activate && pip install -q -r requirements.txt && systemctl restart wan-yitong-sku-matcher && sleep 2 && systemctl is-active wan-yitong-sku-matcher && curl -sS http://127.0.0.1:6578/health && echo && echo OK: published"
