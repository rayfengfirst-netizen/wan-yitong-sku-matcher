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

```bash
cd /opt/wan-yitong-sku-matcher
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart wan-yitong-sku-matcher
```

或复制并使用 `deploy/deploy.sh.example` 为 `deploy/deploy.sh` 后执行。

## 为什么 Cursor 里「让 AI 发布」常会失败

- AI 触发的命令跑在 **隔离环境** 里，**默认拿不到你 Mac 的 ssh-agent**，也不会交互输入密码，所以 `ssh root@8.218.58.28` 常变成 **Permission denied**。
- 即使加上「全部权限」，若 **服务器 `authorized_keys` 里没有当前这台机器正在用的公钥**，同样会拒绝。  
  在本仓库所在机器上实测：`~/.ssh/id_ed25519` 与 `github_ebay_listing` **均未能登录** `8.218.58.28`，说明要么要用 **另一把密钥**，要么要在服务器上 **补登这把公钥**。

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

在仓库根目录执行（需已 `git push`，且 SSH 已能无密码登录服务器）：

```bash
./deploy/remote.sh
```

指定密钥（与服务器 `authorized_keys` 一致的那把）：

```bash
DEPLOY_SSH_IDENTITY=~/.ssh/你的私钥 ./deploy/remote.sh
```

指定主机别名（若已配 `~/.ssh/config`）：

```bash
DEPLOY_HOST=wan-yitong-prod ./deploy/remote.sh
```

配置完成后，在 Cursor 里让 AI 执行 **`./deploy/remote.sh`**（并请求 **全部权限**）时，才有机会和你在终端里一样发布成功。

## 本地开发（Mac）

```bash
cd wan-yitong-sku-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 6578
```

打开 <http://127.0.0.1:6578/>
