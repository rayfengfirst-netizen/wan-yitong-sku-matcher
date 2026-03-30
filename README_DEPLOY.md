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

## 本地开发（Mac）

```bash
cd wan-yitong-sku-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 6578
```

打开 <http://127.0.0.1:6578/>
