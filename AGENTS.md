# 与 AI 协作

- **线上发布**：说「线上发布」即可；AI 会 `git push`（如有未推送改动）并运行 `./deploy/remote.sh`。
- **前提**：本机已与生产机配置好 **SSH 公钥**（见 `README_DEPLOY.md`「一次性配置」）。仅「登录过一次」不等于已配置密钥；需 `ssh-copy-id` 或手动写入 `authorized_keys`。
