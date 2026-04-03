# 与 AI 协作

- **线上发布**：说「线上发布」即可；约定与 **`walmart-listing-production-tool`** 相同：AI 会 `git push` 并执行一条 **`ssh -o BatchMode=yes`** 到 **`8.218.58.28`** 的远程命令（见 `.cursor/rules/online-deploy.mdc`）。也可用本机 **`./deploy/remote.sh`**（等价）。
- **SSH**：公钥在服务器 + 私钥口令需 **`ssh-add`/钥匙串**（见 `README_DEPLOY.md`、`server-ops/SSH_FOR_AGENT.md`）。Agent 子进程若接不到 agent，在本机 **终端**粘贴规则里的同一条 `ssh` 即可。
