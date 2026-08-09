<h1 align="center">Quant-Fletch</h1>

<p align="center">
  A 股 ETF 量化轮动系统 · 零门槛部署 · 开箱即用
</p>

<p align="center">
  <a href="https://github.com/AbelTami/quant-fletch/actions/workflows/unit-test.yml"><img src="https://github.com/AbelTami/quant-fletch/actions/workflows/unit-test.yml/badge.svg" alt="Test" /></a>
  <a href="https://github.com/AbelTami/quant-fletch/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.14-blue.svg" alt="Python 3.14" /></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-%E2%89%A522-brightgreen.svg" alt="Node" /></a>
  <a href="https://github.com/AbelTami/quant-fletch"><img src="https://img.shields.io/github/stars/AbelTami/quant-fletch?style=social" alt="Stars" /></a>
</p>

---

## 这是什么

Quant-Fletch 是一个面向国内量化投资者的 A 股 ETF 轮动系统。核心理念是**用最少的资金门槛，跑最稳健的轮动策略**。

- **品种池**：30 只 A 股 ETF（10 宽基 + 12 行业 + 5 债券 + 3 商品）
- **调仓频率**：日频（每日收盘后运行，非实时刻度）
- **数据来源**：AkShare（免费、无需 API Key），Sina + 东方财富双源互备
- **策略架构**：可插拔，v1.0 内置 5 个策略，支持自定义扩展
- **部署**：`docker compose up` 一条命令

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/AbelTami/quant-fletch.git
cd quant-fletch

# 2. 拉取行情数据（首次约需 10 分钟）
cp .env.example .env
cd api && uv sync && uv run python -m src.data.seed
cd ..

# 3. 启动
docker compose -f docker/docker-compose.yml up

# 4. 打开浏览器
# 前端: http://localhost:3000
# API 文档: http://localhost:8000/docs
```

## 内置策略

| 策略 | 文件 | 核心逻辑 |
|------|------|---------|
| 动量轮动 | `momentum_rotate.py` | N 日涨跌幅排序，持有 Top K |
| 多因子打分 | `multi_factor.py` | 动量 + 波动率 + 成交量 + 夏普 4 因子加权 |
| 趋势 + MA 过滤 | `trend_ma.py` | MA 均线过滤趋势 + 动量打分 |
| 风险平价 | `risk_parity.py` | 波动率倒数加权，等风险贡献 |
| 止损动量 | `stop_loss_momentum.py` | 动量轮动 + 移动止损 |

所有策略继承 `BaseStrategy` ABC，实现 `register()` → `warmup()` → `prepare_features()` → `score()` → `allocate()` → `to_signals()` → `execute()` 9 步生命周期。添加自定义策略只需继承基类并放入 `strategies/` 目录——`importlib` 自动发现。

## 技术栈

| 层 | 选型 | 理由 |
|-----|------|------|
| 前端框架 | Nuxt 4 | SSR + 静态生成，Vue 3 生态 |
| CSS 引擎 | UnoCSS (presetWind4) | 原子化 CSS，按需生成 |
| 图表 | Lightweight Charts + ECharts | K 线 + 复杂图表组合 |
| 动效 | GSAP | 高性能 DOM 动画 |
| 后端 | FastAPI (Python 3.14) | 异步原生，自动 OpenAPI 文档 |
| 分析数据库 | DuckDB | 列存 OLAP，秒级聚合 |
| 持久化 | PostgreSQL + TimescaleDB | 时序最优，托管元数据 |
| DataFrame | polars + pandas | polars 主力计算，pandas 对接 VectorBT |
| 回测引擎 | 自研 + VectorBT 适配 | 双模互验，PIT 安全 |
| 数据源 | AkShare → Sina + 东方财富 | 免费零门槛 |
| 包管理 | uv (Python) + pnpm (Node) | 快，lockfile 稳定 |
| ESLint | `@antfu/eslint-config` | 零配置，antfu 风格 |
| CI/CD | `sxzz/workflows` | autofix + unit-test 可复用工作流 |

## 项目结构

```
quant-fletch/
├── api/                    # Python FastAPI 后端
│   ├── src/
│   │   ├── backtest/       # 回测引擎（自研 + VectorBT 适配）
│   │   ├── data/           # 数据管线（日历/源适配/校验/清洗/因子）
│   │   ├── db/             # DuckDB + PostgreSQL 连接管理
│   │   ├── server/         # FastAPI 路由（ETF/策略/回测/系统）
│   │   └── strategies/     # 策略插件（自动发现）
│   ├── tests/              # pytest + pytest-cov
│   └── pyproject.toml      # uv 项目配置
├── web/                    # Nuxt 4 前端
│   ├── app/
│   │   ├── components/     # Vue 组件
│   │   ├── composables/    # useETFData / useStrategy / useBacktest / useMotion
│   │   ├── pages/          # 仪表盘 / 策略 / 信号 / 数据浏览 / 系统设置
│   │   └── types/          # TypeScript 接口
│   ├── tests/              # Vitest + Playwright E2E
│   ├── nuxt.config.ts      # imports.autoImport: false
│   └── uno.config.ts       # 语义 token 系统
├── shared/schemas/         # 跨端类型契约（建设中）
├── docker/                 # Dockerfile + docker-compose
└── .github/workflows/      # CI（autofix + unit-test）
```

## 架构

### 数据管线

```
交易日历 → 源适配器 → 原始湖 → 校验器 → 清洗器 → 因子服务 → 策略
    ↑                      ↑                    ↑
   Parquet               DuckDB              FeatureService
  (Sina 校准)          (按 code/日期分区)     (PIT 安全)
```

### 策略生命周期

```
register() → warmup() → prepare_features() → score() → allocate() → to_signals() → execute()
                                                          ↑
                                                   7 个 frozen dataclass
                                                   (不可变配置)
```

### 回测引擎

```
                  ┌── SelfLoopBacktester（自研，PIT 安全）
BacktestConfig ───┤
                  └── VectorBTAdapter（第三方，交叉验证）
```

## 设计原则

- **Point-in-Time 正确性** — 调仓日只看到当日之前的数据，杜绝未来信息泄露
- **Frozen Dataclass** — 所有配置对象不可变，杜绝运行时意外修改
- **显式导入** — Nuxt/Nitro 关闭自动导入，所有依赖从 `#imports` 显式引入
- **Ponytail**（后端） — 不到需要时不加功能，最短 diff，注释标记决策边界
- **双数据库** — DuckDB 做分析查询（列存），PostgreSQL 做事务持久化（行存）
- **双数据源** — Sina + 东方财富互备，单源故障不阻塞流程

## 已知限制（v1.0）

这是 v1.0 版本，存在以下已知问题，正在迭代修复中：

- 日线尚未启用前复权（种子流程使用 Sina 不复权数据）
- 行业 ETF 与宽基 ETF 共用同一套动量因子，尚未引入申万行业指数
- 回测结果仅存内存，重启丢失（Phase 1 接入 PostgreSQL 持久化）
- FeatureService 因子引擎已实现但尚未接入回测主循环
- 分钟线数据已拉取但回测引擎仅支持日频

详见 [迭代方案](https://github.com/AbelTami/quant-fletch/blob/main/docs/迭代/README.md)。

## 贡献

欢迎 Issue 和 PR。开始前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

开发环境：

```bash
# Backend
cd api && uv sync --all-extras && uv run pytest

# Frontend
cd web && pnpm i && pnpm dev
```

## 许可证

MIT © [Quant Fletch](https://github.com/quantfletch)
