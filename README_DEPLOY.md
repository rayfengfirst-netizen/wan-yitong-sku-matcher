# 线上部署（端口 **6578**）

> 发布目标服务器：`root@8.218.58.28`  
> GitHub：<https://github.com/rayfengfirst-netizen/wan-yitong-sku-matcher.git>

**生产入口（公网）**：<http://8.218.58.28:6578/>

## 路径与端口

| 项 | 值 |
|----|-----|
| 代码目录（建议） | `/opt/wan-yitong-sku-matcher` |
| 对外端口 | **6578**（`uvicorn --host 0.0.0.0 --port 6578`） |
| 进程 | systemd：`wan-yitong-sku-matcher.service` |
| 数据目录 | 项目下 `data/`（SQLite 任务历史、每次匹配结果 xlsx，**勿删**；已写入 `.gitignore`） |

云厂商安全组需放行 **TCP 6578**（若日后改为 Nginx 反代，可改为监听 `127.0.0.1:6578` 并只开放 80/443）。

## 首次部署（在服务器上执行）

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/rayfengfirst-netizen/wan-yitong-sku-matcher.git
cd /opt/wan-yitong-sku-matcher
sudo python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo cp deploy/wan-yitong-sku-matcher.service.example /etc/systemd/system/wan-yitong-sku-matcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now wan-yitong-sku-matcher
curl -sS http://127.0.0.1:6578/health
```

浏览器访问：<http://8.218.58.28:6578/>

## 日常发布

**服务器上**（已 SSH 登录后）可多行执行；**本机一条命令**（与 walmart Agent 规则同型）：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 root@8.218.58.28 'cd /opt/wan-yitong-sku-matcher && git pull && . .venv/bin/activate && pip install -q -r requirements.txt && systemctl restart wan-yitong-sku-matcher && sleep 2 && systemctl is-active wan-yitong-sku-matcher && curl -sS http://127.0.0.1:6578/health'
```

或在本机仓库执行 **`./deploy/remote.sh`**（等价）。

```bash
cd /opt/wan-yitong-sku-matcher
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wan-yitong-sku-matcher
```

或复制并使用 `deploy/deploy.sh.example` 为 `deploy/deploy.sh` 后在**服务器**上执行。

## 与沃尔玛刊登生产工具（同工作区）对齐

**发布口令与流程**与 `walmart-listing-production-tool` 的 Agent 约定相同：一条 **`ssh -o BatchMode=yes …`**，且 Cursor 里执行须 **`required_permissions: ["all"]`**。差别只是本服务在 **`8.218.58.28`**、目录 **`/opt/wan-yitong-sku-matcher`**、端口 **6578**。

## 为什么有时「本机终端能发、让 AI 发却 Permission denied」

- **你在 Cursor 终端 / Mac 终端里手动执行** 与 **对话里 Agent 调用的命令** 可能不在同一环境：Agent 子进程**常常接不到 ssh-agent**，也**不能交互输入**私钥 passphrase，于是 `BatchMode=yes` 下容易失败。  
- 这与连 **8.218** 还是 **8.221** 无关；同一 Agent 环境对两台机往往**同时**成功或**同时**失败。  
- 详细排查与钥匙串配置见工作区 **`server-ops/SSH_FOR_AGENT.md`**（若仓库在 `Desktop/cursor/` 下）。

## 一次性配置（做完后本机 / Cursor 用脚本都能发）

1. 在你 **平时能登录成功** 的终端里执行（看实际用的是哪把钥匙）：

   ```bash
   ssh -v root@8.218.58.28 true 2>&1 | grep 'Offering public key'
   ```

2. 若你希望用本机 **`~/.ssh/id_ed25519` 登录**，而服务器尚未登记，执行一次（需能登录，例如先密码）：

   ```bash
   ssh-copy-id -i ~/.ssh/id_ed25519.pub root@8.218.58.28
   ```

3. 可选：写 `~/.ssh/config`，固定主机与密钥（把路径改成你 **Offering** 里那把）：

   ```sshconfig
   Host wan-yitong-prod
     HostName 8.218.58.28
     User root
     IdentityFile ~/.ssh/id_ed25519
     IdentitiesOnly yes
   ```

## 本机发布脚本（推荐）

在仓库根目录执行（需已 `git push`，且 SSH 已能登录服务器）：

```bash
./deploy/remote.sh
```

### 私钥带 passphrase（很常见）

`ssh-copy-id` 已提示公钥在服务器上，但 **`./deploy/remote.sh` 仍 Permission denied**，通常是因为脚本在非交互模式下无法用键盘输入密码解锁私钥。

**做法（二选一）：**

1. **当前终端会话先加载密钥**（输一次 passphrase）：

   ```bash
   ssh-add ~/.ssh/id_ed25519
   ./deploy/remote.sh
   ```

2. **macOS：把密钥交给钥匙串**，以后本机终端 / 部分场景可自动解锁：

   ```bash
   ssh-add --apple-use-keychain ~/.ssh/id_ed25519
   ```

   若尚未配置，可在 `~/.ssh/config` 里为对应 `Host` 增加：

   ```sshconfig
   Host 8.218.58.28
     HostName 8.218.58.28
     User root
     IdentityFile ~/.ssh/id_ed25519
     AddKeysToAgent yes
     UseKeychain yes
   ```

脚本**默认**已带 `BatchMode=yes`（与 walmart 规则一致）。仅在终端里**未** `ssh-add`、需要**交互输入** passphrase 时：`SSH_BATCH_MODE=no ./deploy/remote.sh`。

指定密钥（与服务器 `authorized_keys` 一致的那把）：

```bash
DEPLOY_SSH_IDENTITY=~/.ssh/你的私钥 ./deploy/remote.sh
```

指定主机别名（若已配 `~/.ssh/config`）：

```bash
DEPLOY_HOST=wan-yitong-prod ./deploy/remote.sh
```

项目规则与 walmart 相同：你说 **「线上发布」** 时，AI 会 `git push` 并执行**一条**与上文等价的 **`ssh -o BatchMode=yes …`**（见 `.cursor/rules/online-deploy.mdc`）。若 Agent 仍 denied，在本机 **Cursor 终端**粘贴同一条命令即可（环境与你手动操作一致）。

## 本地开发（Mac）

```bash
cd wan-yitong-sku-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 6578
```

打开 <http://127.0.0.1:6578/>
