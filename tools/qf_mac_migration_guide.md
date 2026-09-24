# 迁移到 Mac mini M4 操作指南

> 目标：在本机（Windows / x86_64）之外，于 Mac mini M4（ARM64）上跑起 quant-fletch。
> 本指南基于对仓库的实际核查，不是通用 Docker 教程。

---

## 一、⚠️ 最大的坑：不要 `git clone`

本机 `git status` 实测：**38 项未提交改动 + 6 个未跟踪的新文件**，
且本地分支 `main` 与 `origin/main` **完全同步（领先 0 个提交）**。

**也就是说：GitHub 上的版本不含本轮全部工作。** 直接 clone 会缺：

| 缺失内容 | 后果 |
|---|---|
| `api/src/strategies/ma10_trend.py`（未跟踪） | **MA10 策略整个不存在**，只剩 6 个策略 |
| `api/src/data/price_adjust.py`（未跟踪） | 价格断层不修复，回测还是会被假暴跌污染 |
| `web/app/config/labels.ts`（未跟踪） | 前端中文文案层缺失，**构建可能直接失败** |
| `sector_rotate.py` / `shenwan.py` / `base.py` 等 12 个策略文件改动 | 行业轮动不可复现、因子参数恒为默认值、5 个策略只买不卖 |
| 调优后的默认参数 | 用回旧的低效参数 |
| `tools/`（未跟踪） | 全部诊断脚本 |

### 两条正确的搬运方式

**方案 A（推荐）：先提交并推送，再在 Mac 上 clone**

```bash
# 在 Windows 本机
cd "D:/桌面/etf/quant-fletch"
git add -A                       # 必须 -A，否则 6 个新文件不会被纳入
git commit -m "feat: 前复权修复 + 目标组合模式 + 行业数据/确定性修复 + 参数调优"
git push origin main

# 在 Mac mini
git clone https://github.com/AbelTami/quant-fletch.git
cd quant-fletch
```

**方案 B：直接拷贝目录**（不想动远端时）

用 `rsync` 排除无用的大目录：

```bash
# 在 Mac 上执行，<源> 指向共享目录或移动硬盘上的项目
rsync -av --progress "<源>/quant-fletch/" ./quant-fletch/ \
  --exclude node_modules \
  --exclude .venv \
  --exclude .git \
  --exclude '*.duckdb' \
  --exclude '*.duckdb.wal'
```

> `node_modules`、`.venv`、`*.duckdb` 一定要排除 ——
> 前两者含 **Windows x64 的二进制**，拷过去会污染 ARM64 环境。

---

## 二、必须修改的配置（否则界面连不上后端）

`docker/docker-compose.yml` 里 `nuxt.build.args` 当前是：

```yaml
API_BASE_URL: http://101.42.40.10:10004
VITE_WS_ORIGIN: ws://101.42.40.10:10004
```

**这是你 Windows 机器的 frp 内网穿透地址。** Mac 上必须改回内网直连：

```yaml
API_BASE_URL: http://api:8000
VITE_WS_ORIGIN: ws://localhost:18000
```

同时把下面 `environment:` 里的 `API_BASE_URL` 一并改掉。

> 这两个值是**构建期注入**的（`nuxt build` 时求值），改完必须重新 build 才会生效；
> 只改 runtime environment 无效。

### `.env` 文件

`.env` 被 `.gitignore` 忽略（第 35 行），**不会随 clone 过去**。在 Mac 上新建：

```bash
cat > .env <<'EOF'
DB_PASSWORD=changeme
AKSHARE_TIMEOUT=30
AKSHARE_RETRY_DELAY=3
BACKTEST_MAX_DAYS=3000
EOF
```

（`DB_PASSWORD` 只在首次初始化数据库时生效；新机器是全新数据卷，填什么都行。）

---

## 三、启动

```bash
cd quant-fletch
docker compose -f docker/docker-compose.yml up -d --build
```

首次会构建 3 个镜像，约 5~10 分钟。检查状态：

```bash
docker compose -f docker/docker-compose.yml ps
# 三个容器都应为 healthy / Up
```

---

## 四、初始化数据（必做，新机器数据卷是空的）

DuckDB / PostgreSQL 都是**命名卷**，不会跟着代码走，Mac 上是全新空库。

```bash
curl -X POST http://localhost:18000/api/v1/system/seed \
  -H "Content-Type: application/json" \
  -d '{"mode":"full"}'
```

或打开 <http://localhost:3000/setup> 点初始化按钮。**约 10 分钟**（要下载 34 只 ETF 的日线/分钟线 + 31 个申万行业）。

完成后自检：

```bash
curl -s http://localhost:18000/api/v1/system/status
# 期望: {"data":{"status":"ready","etfs_available":34,"etfs_total":34,...}}
```

> 本次 seed 会自动执行「断层检测 + 前复权回补」（`clean_etf_data` 的第二步 pipeline），
> 无需额外操作。

---

## 五、架构兼容性核查结论

已逐项确认，**这个项目迁移到 ARM64 基本没有障碍**：

| 检查项 | 结果 |
|---|---|
| `python:3.14-slim` | 官方多架构镜像，含 linux/arm64 |
| `node:22-alpine` | 官方多架构镜像，含 linux/arm64 |
| `pgvector/pgvector:pg16` | 多架构（官方仓库提供 arm64 清单） |
| `api/uv.lock` | 含 **109 条 aarch64** 条目，`uv sync --frozen` 可解析 |
| Python 依赖 | 全部有 ARM64 wheel（polars/duckdb/pyarrow/numpy/psycopg[binary] 等） |
| `pnpm-lock.yaml` 原生包 | `@rollup/rollup-linux-arm64-gnu`、`@esbuild/linux-arm64`、`lightningcss-linux-arm64-gnu` **均在** |
| `sharp` | 不是依赖（0 处引用），无影响 |
| `.dockerignore` | 已排除 `node_modules` / `.nuxt` / `.venv` / `*.duckdb`，`COPY . .` 不会带入 Windows 二进制 |
| Dockerfile / compose 行尾 | **全部 LF**（无 CRLF 换行符问题） |
| shell 脚本 | 项目内没有 `.sh` 脚本，不存在可执行位/CRLF 问题 |
| `requires-python` | `>=3.14`，与基础镜像一致 |

在 Mac 上可自行复核镜像架构：

```bash
docker buildx imagetools inspect pgvector/pgvector:pg16 | grep -E "linux/(amd64|arm64)"
```

---

## 六、Mac 特有的注意点

1. **端口不用改**。`18000:8000` 与 `3000:3000` 在 macOS 上都能正常绑定。
   compose 里那段「Windows 保留端口 7948-8047 覆盖 8000」的注释在 Mac 上不适用，
   属于历史原因，留着无影响。
2. **不要从 Windows 拷贝镜像**。`docker save` / `load` 过来的是 amd64 镜像，
   在 M4 上会走 Rosetta 模拟、慢且可能出错。**必须在 Mac 上重新 build**（本指南的流程即是）。
3. **给 Docker 分配足够内存**。Docker Desktop → Settings → Resources，
   建议 **≥ 8 GB**（回测涉及 7 万多行行情 + 因子计算，内存吃紧会 OOM）。
4. **文件共享性能**。本项目只用 Docker **命名卷**，没有把源码 bind mount 进容器，
   因此不受 macOS 文件共享慢的影响 ✓。
5. **`name: quant-fletch` 必须保留**。它固定了 compose 项目名，
   避免容器/卷按目录名命名产生冲突。
6. **外网访问**。若想让 Mac 对外提供服务，需要把 frp 隧道重新指向 Mac 的地址；
   原先指向 Windows 的那条隧道对 Mac 无效。

---

## 七、验证清单

```bash
# 1. 容器状态
docker compose -f docker/docker-compose.yml ps

# 2. 后端健康
curl -s http://localhost:18000/health
curl -s http://localhost:18000/api/v1/system/status

# 3. 策略数量（应为 7 个，若只有 6 个说明 ma10_trend.py 没搬过来）
curl -s http://localhost:18000/api/v1/strategies | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']), '个策略')"

# 4. 前端页面（都应为 200）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/dashboard

# 5. 断层是否已修（应无输出）
docker run --rm -v quant-fletch_duckdb_data:/app/data quant-fletch-api \
  python -c "
import duckdb
c=duckdb.connect('/app/data/quant.duckdb',read_only=True)
print('etf_daily',c.execute('SELECT count(*) FROM etf_daily').fetchone()[0],'行 /',c.execute('SELECT count(DISTINCT code) FROM etf_daily').fetchone()[0],'只')"
```

**第 3 步是最关键的**：`ma10_trend.py` 是未跟踪文件，最容易漏掉。
只有 6 个策略 = 搬运不完整，需要回去用方案 A 或 B 重做。
