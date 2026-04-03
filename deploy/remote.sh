#!/usr/bin/env bash
# 从本机一键发布到生产（与 walmart 生产工具同源：默认 BatchMode=yes）
#
# 私钥带 passphrase：须先 ssh-add（或钥匙串），否则 BatchMode 下会 Permission denied。
# 终端里未进 agent、需要交互输 passphrase： SSH_BATCH_MODE=no ./deploy/remote.sh
set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-root@8.218.58.28}"
REMOTE_DIR="${REMOTE_DIR:-/opt/wan-yitong-sku-matcher}"

# 与 walmart-listing agent-workflow 一致，便于 Agent / CI 与人工同一行为
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20)
if [[ "${SSH_BATCH_MODE:-}" == "no" ]]; then
  SSH_OPTS=(-o ConnectTimeout=25)
fi
if [[ -n "${DEPLOY_SSH_IDENTITY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_SSH_IDENTITY" -o IdentitiesOnly=yes)
fi

# BatchMode 不能交互输入私钥口令，agent 里必须有已解锁的密钥
if [[ "${SSH_BATCH_MODE:-}" != "no" ]] && ! ssh-add -l >/dev/null 2>&1; then
  echo "deploy/remote.sh: ssh-agent 里没有可用密钥（你刚看到的 Permission denied 通常就是这个原因）。" >&2
  echo "" >&2
  echo "在本终端先执行其一：" >&2
  echo "  ssh-add ~/.ssh/id_ed25519          # 会提示输入一次 passphrase" >&2
  echo "  ssh-add --apple-use-keychain ~/.ssh/id_ed25519   # macOS 写入钥匙串，以后省事" >&2
  echo "若提示无法连接 agent：" >&2
  echo "  eval \"\$(ssh-agent -s)\" && ssh-add ~/.ssh/id_ed25519" >&2
  echo "不加载 agent、允许交互输口令：" >&2
  echo "  SSH_BATCH_MODE=no ./deploy/remote.sh" >&2
  exit 1
fi

RDIR=$(printf %q "$REMOTE_DIR")
exec ssh "${SSH_OPTS[@]}" "$DEPLOY_HOST" \
  "set -euo pipefail; cd $RDIR && git pull && . .venv/bin/activate && pip install -q -r requirements.txt && systemctl restart wan-yitong-sku-matcher && sleep 2 && systemctl is-active wan-yitong-sku-matcher && curl -sS http://127.0.0.1:6578/health && echo && echo OK: published"
