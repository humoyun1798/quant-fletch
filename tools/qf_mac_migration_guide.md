# 迁移到 Mac mini M4 操作指南

> 目标：在本机（Windows / x86_64）之外，于 Mac mini M4（ARM64）上跑起 quant-fletch。
> 本指南基于对仓库的实际核查，不是通用 Docker 教程。

---

## TL;DR — 改动清单

### ⚠️ 先分清两个版本（否则行号对不上）

| 版本 | 行数 | 状态 |
|---|---|---|
| **工作副本**（你在 Windows 上实际用的） | **111 行** | 已修好的可用版本 |
| **已提交 / GitHub 版** | **66 行** | **原始仓库的破损版本，跑不起来** |

两者相差 50 行，且**差异不只是注释**。已提交版有 5 处致命错误：

| 问题 | 已提交版 | 后果 |
|---|---|---|
| 第 1 行无 `name:` | 直接 `services:` | 项目名取目录名 `docker`，与同名目录项目的卷撞车 |
| `db.cap_drop: ALL`（第 19 行） | 有 | **postgres 容器立即退出**（chmod/setuid 被剥夺）|
| **api 段无 `ports:`** | 缺失 | 宿主机访问不到 18000 |
| api healthcheck 用 `curl`（第 35 行） | python:3.14-slim 无 curl | **healthcheck 恒失败 → api 永不 healthy → nuxt 永不启动** |
| 无任何 `tmpfs` | 缺失 | `read_only: true` 下 /tmp 不可写，报只读文件系统 |

**结论：必须迁移工作副本，不能 clone。** 这也就是第一节那个警告的实证。

### 要改的地方（按内容找，不按行号）

打开**工作副本**的 `docker/docker-compose.yml`，找到 `nuxt:` 服务里的 `build:` → `args:`：

```yaml
    build:
      context: ..
      dockerfile: docker/Dockerfile.web
      args:
        API_BASE_URL: http://101.42.40.10:10004     ← 改成 http://api:8000
        VITE_WS_ORIGIN: ws://101.42.40.10:10004     ← 不用改
    environment:
      API_BASE_URL: http://101.42.40.10:10004       ← 改成 http://api:8000
```

即：**两处 `API_BASE_URL` 改成 `http://api:8000`；`VITE_WS_ORIGIN` 保持不动。**

> 若你用的是 66 行版：它**没有 `args:` 段**，而 `environment.API_BASE_URL` 本来就是
> `http://api:8000` —— 地址这块无需改。但**先得把上表 5 处错误修好，否则起不来。**

### 不需要改的

- `docker/Dockerfile.api`、`docker/Dockerfile.web` — 不用动
- 端口 `18000:8000` / `3000:3000` — macOS 上照常可用
- `name: quant-fletch`、`volumes`、`read_only`、`tmpfs`、`cap_drop` — 保留
- `.env` — **可选**，不建也能跑
- 任何前端 / 后端源码 — 不用动

---

## 一、⚠️ 最大的坑：不要 `git clone`

本机 `git status` 实测：**38 项未提交改动 + 6 个未跟踪的新文件**，
且本地分支 `main` 与 `origin/main` **完全同步（领先 0 个提交）**。

**也就是说：GitHub 上的版本不含本轮全部工作**，而且**连启动都做不到**
（`docker/docker-compose.yml` 已提交版只有 66 行、含 5 处致命错误，
详见上方 TL;DR 的两版本对照）。

直接 clone 会缺：

| 缺失内容 | 后果 |
|---|---|
| `docker/docker-compose.yml` 的 50 行修复 | **容器起不来**（cap_drop 致 postgres 退出、api 无端口映射、healthcheck 用 curl 恒失败）|
| `docker/Dockerfile.api` / `Dockerfile.web` 修复 | 构建失败 |
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

**这是 Windows 机器的 frp 隧道地址，Mac 上必须改。**

### 关键：这两个值的性质完全不同，不能一起改

| 变量 | 谁在用 | 该填什么 |
|---|---|---|
| `API_BASE_URL` | **SSR 侧**（容器内的服务端请求） | **永远填 `http://api:8000`** |
| `VITE_WS_ORIGIN` | **浏览器侧**（直连 WebSocket） | 看是否需要外网访问 |

**`API_BASE_URL` 不要指向公网隧道** —— 它是容器内的服务端请求，走 Docker 内网即可。
指向公网有两个坏处：每次 SSR 绕一圈公网；而且**隧道一断，本地 `localhost:3000`
也会打不开**（2026-09-21 实际发生过：界面显示"数据初始化"页，其实数据完好，
只是 SSR 拿不到后端、被中间件跳转了）。

**所以：Mac 上有内网穿透，也只改 `VITE_WS_ORIGIN` 这一个值。**

### 情况 A：Mac 上开自己的内网穿透（要外网访问界面）

```yaml
    build:
      args:
        API_BASE_URL: http://api:8000                # 恒为内网, 不要动
        VITE_WS_ORIGIN: ws://101.42.40.10:10004      # 沿用原有隧道地址
    environment:
      API_BASE_URL: http://api:8000
```

即：**沿用原隧道 API 地址时，第 92 行不用改，净改动只有第 91、94 两行。**

**⚠️ 两条隧道，别只开一条：**

| 用途 | Mac 本地端口 | 远程端口 | 说明 |
|---|---|---|---|
| **界面** | `3000` | 需新开（如 `10005`） | 不开这条，**外网打不开 UI**，只能在本机用 |
| **后端 API** | `18000` | `10004`（沿用） | 浏览器连 WebSocket 推回测进度；不开这条，**回测会卡在"运行中"** |

**⚠️ `10004` 同时只能被一台机器占用。** 若 Windows 那台也把 frpc 开起来，
两个客户端会争 `10004`，后连上的那个绑定失败（frps 日志报端口已占用）。
要么**只跑一台**，要么给 Mac 换别的远程端口。

### 情况 B：只在局域网用（不开穿透）

```yaml
    build:
      args:
        API_BASE_URL: http://api:8000
        VITE_WS_ORIGIN: ws://localhost:18000
    environment:
      API_BASE_URL: http://api:8000
```

> 这两个值是**构建期注入**的（`nuxt build` 时求值），改完必须重新 build 才会生效；
> 只改 runtime environment 无效。

### 已核查：换公网地址不需要额外放行

| 检查项 | 结果 |
|---|---|
| 后端 CORS | **完全没有配置**，无来源白名单 |
| WS 端点 | 直接 `websocket.accept()`，**不校验 Origin** |
| 前端 Nitro | 未设 `allowedHosts`，不会拒绝未知 Host |
| WS 地址来源 | 前端**直接用** `VITE_WS_ORIGIN` 当 `WS_BASE`（见 `web/app/config/api.ts`）；未注入时回落同源 —— 而 Nuxt 容器不提供 WS 端点，故该值**必须**填对 |

### `.env` 是可选的（实测：不建也能跑）

`.env` 被 `.gitignore` 忽略、不会随 clone 过去。但**全仓库核查后确认它并不必需**：

| 键 | 实际使用位置 | 结论 |
|---|---|---|
| `DB_PASSWORD` | 只在 `docker-compose.yml` 第 18、45 行，且都写成 `${DB_PASSWORD:-changeme}` | **有默认值**，不建也用 changeme |
| `AKSHARE_TIMEOUT` | **全仓库无任何引用** | 死配置 |
| `AKSHARE_RETRY_DELAY` | **全仓库无任何引用** | 死配置 |
| `BACKTEST_MAX_DAYS` | **全仓库无任何引用** | 死配置 |

所以 Mac 上**可以不建 `.env`**，直接启动即可。若要建，内容照旧：

```bash
cat > .env <<'EOF'
DB_PASSWORD=changeme
AKSHARE_TIMEOUT=30
AKSHARE_RETRY_DELAY=3
BACKTEST_MAX_DAYS=3000
EOF
```

> 注意：已在 Windows 上初始化过的数据库卷，若换了 `DB_PASSWORD`，
> 旧卷里的口令不会跟着变，会认证失败。**新机器是全新卷，随意。**

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
6. **外网访问（Mac 自己开穿透）**。分两条隧道，见第二节「情况 A」：
   `3000 → 界面`、`18000 → 后端 API`。只用一条的话，
   要么外网打不开界面，要么回测进度卡住。
   原先指向 Windows 的 `10004` 若还在用，**Mac 必须挑别的远程端口**。
7. **两台机器同时跑要分开端口**。如果 Windows 那台不停、Mac 也开服务，
   远程端口必须错开（例如 Windows 10004 / Mac 10005+10006），
   否则 frps 上同一个远程端口会被抢占，表现为时通时不通。

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
