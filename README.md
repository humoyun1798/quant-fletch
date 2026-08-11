<h1 align="center">Quant-Fletch</h1>

<p align="center">
  <strong>A 股 ETF 量化轮动系统</strong> · 零门槛部署 · 开箱即用
</p>

<p align="center">
  <a href="https://github.com/AbelTami/quant-fletch/actions/workflows/unit-test.yml"><img src="https://github.com/AbelTami/quant-fletch/actions/workflows/unit-test.yml/badge.svg" alt="Test" /></a>
  <a href="https://github.com/AbelTami/quant-fletch/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.14-blue.svg" alt="Python 3.14" /></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-%E2%89%A522-brightgreen.svg" alt="Node" /></a>
  <a href="https://github.com/AbelTami/quant-fletch"><img src="https://img.shields.io/github/stars/AbelTami/quant-fletch?style=social" alt="Stars" /></a>
</p>

---

## 目录

- [这是什么](#这是什么)
- [特性](#特性)
- [快速开始](#快速开始)
- [内置策略](#内置策略)
- [分配方法](#分配方法)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [架构](#架构)
- [设计原则](#设计原则)
- [已知限制](#已知限制)
- [开发](#开发)
- [许可证](#许可证)

## 这是什么

Quant-Fletch 是一个面向国内量化投资者的 A 股 ETF 轮动系统。核心理念：**用最少的资金门槛，跑最稳健的轮动策略**。

- **品种池** — 30 只 A 股 ETF：10 宽基 + 12 行业 + 5 债券 + 3 商品
- **调仓频率** — 日频（每日收盘后运行，非实时刻度）
- **数据来源** — AkShare（免费、无需 API Key），Sina + 东方财富双源互备
- **策略架构** — 可插拔设计，内置 5 个策略 + 6 种分配算法，支持自定义扩展
- **回测引擎** — 自研 PIT 安全回测器 + VectorBT 交叉验证双模
- **部署方式** — `docker compose up` 一条命令

## 特性

- [x] **5 个内置策略** — 动量轮动、多因子打分、趋势 MA 过滤、风险平价、止损动量
- [x] **6 种分配算法** — 等权、最大分散度、最小方差、波动率倒数、风险平价、Black-Litterman
- [x] **Black-Litterman 模型** — 完整贝叶斯框架：策略打分映射观点 + 市值均衡先验 + 梯度投影 MV 优化
- [x] **PIT 安全回测** — 调仓日仅见当日之前数据，杜绝未来信息泄露
- [x] **双数据源互备** — Sina + 东方财富，单源故障不阻塞流程
- [x] **双数据库引擎** — DuckDB 列存做分析查询，PostgreSQL + TimescaleDB 做事务持久化
- [x] **WebSocket 实时回测** — 分步进度推送，支持中途刷新恢复
- [x] **Optuna 超参优化** — 自动搜索最优参数组合
- [x] **Docker 一键部署** — 前端 + 后端 + PostgreSQL 全部容器化

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/AbelTami/quant-fletch.git
cd quant-fletch

# 2. 拉取行情数据（首次约需 10 分钟）
cp .env.example .env
cd api && uv sync && uv run python -m src.data.seed
cd ..

# 3. 启动全部服务
docker compose -f docker/docker-compose.yml up

# 4. 打开浏览器
# 前端仪表盘:  http://localhost:3000
# API 交互文档: http://localhost:8000/docs
```

## 内置策略

| 策略 | 文件 | 核心逻辑 | 可选分配方法 |
|------|------|---------|-------------|
| 动量轮动 | `momentum_rotate.py` | N 日涨跌幅排序，持有 Top K | Equal / BL |
| 多因子打分 | `multi_factor.py` | 动量 + 波动率 + 成交量 + 夏普 4 因子加权 | Equal / MaxDiv / MinVar / InvVol |
| 趋势 + MA 过滤 | `trend_ma.py` | MA 均线过滤趋势 + 动量打分 | Equal / BL |
| 风险平价 | `risk_parity.py` | 波动率倒数加权，等风险贡献 | 内置风险平价 |
| 止损动量 | `stop_loss_momentum.py` | 动量轮动 + 移动止损 | Equal |

所有策略继承 `BaseStrategy` ABC，实现 `register()` → `warmup()` → `prepare_features()` → `score()` → `allocate()` → `to_signals()` → `execute()` 9 步生命周期。添加自定义策略只需继承基类并放入 `strategies/` 目录 — `importlib` 自动发现。

## 分配方法

`allocation.py` 提供 6 种权重分配算法，策略通过 `alloc_method` 参数切换：

| 方法 | 算法 | 适用场景 |
|------|------|---------|
| `equal` | 等权分配 | 默认，简单稳健 |
| `max_div` | 最大分散度 | 最大化 Diversification Ratio |
| `min_var` | 最小方差 | 全局最小方差组合（无约束） |
| `inv_vol` | 波动率倒数加权 | 低波高配，高波低配 |
| `bl` | **Black-Litterman** | 融合主观观点与市场均衡 |
| _(内置)_ | 风险平价 | 等风险贡献（`risk_parity.py` 专用） |

### Black-Litterman 算法

BL 分配 (`alloc_method='bl'`) 将策略动量打分转化为预期收益观点，与市场均衡先验进行贝叶斯融合：

```
π = λ·Σ·w_mkt          # 均衡收益（市值权重从 etf_info.fund_size 读取）
P, Q                    # 观点矩阵：高/低动量 → 正/负预期收益
Ω = diag(P·(τΣ)·P')   # 观点不确定性（Idzorek 置信度加权）
μ_BL = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ · [(τΣ)⁻¹π + P'Ω⁻¹Q]   # 贝叶斯后验
Σ_BL = Σ + posterior    # 后验协方差
max w'μ_BL - (λ/2)w'Σ_BL w   s.t. w ≥ 0, Σw = 1    # 梯度投影 MV 优化
```

关键实现：
- 梯度投影法解长仓 MV 优化 — 乘性更新保证非负，不引入 scipy 依赖
- Duchi et al. 2008 单纯形投影 — O(N log N)，处理约束边界
- 协方差奇异 → 等权 fallback；fund_size 缺失 → 等权市场先验
- τ 默认 1/60，λ 默认 2.5（保守参数），view_confidence_scale 默认 1.0
- 22 个单元测试覆盖数值精度、边界、视图冲突、降级路径

## 技术栈

| 层 | 选型 | 说明 |
|-----|------|------|
| 前端框架 | Nuxt 4 (Vue 3) | SSR + 静态生成 |
| CSS 引擎 | UnoCSS (presetWind4) | 原子化 CSS，按需生成 |
| 设计系统 | `@antfu/design` | 语义 Token，Light/Dark 双主题 |
| 图表 | Lightweight Charts + ECharts | K 线 + 复杂图表组合 |
| 动效 | GSAP | 高性能 DOM 动画 |
| 后端框架 | FastAPI (Python 3.14) | 异步原生，自动 OpenAPI 文档 |
| 分析数据库 | DuckDB | 列存 OLAP，秒级聚合 |
| 持久化 | PostgreSQL + TimescaleDB | 时序最优，托管元数据 |
| DataFrame | polars + pandas | polars 主力计算，pandas 对接 VectorBT |
| 回测引擎 | 自研 + VectorBT 适配 | 双模互验，PIT 安全 |
| 超参优化 | Optuna | 贝叶斯搜索，自动剪枝 |
| 数据源 | AkShare → Sina + 东方财富 | 免费零门槛 |
| 包管理 | uv (Python) + pnpm (Node) | 快速，lockfile 稳定 |
| ESLint | `@antfu/eslint-config` | 零配置，antfu 风格 |
| CI/CD | `sxzz/workflows` | autofix + unit-test |

## 项目结构

```
quant-fletch/
├── api/                        # Python FastAPI 后端
│   ├── src/
│   │   ├── backtest/           # 回测引擎（自研 + VectorBT 适配）
│   │   ├── data/               # 数据管线（日历 / 源适配 / 校验 / 清洗 / 因子）
│   │   ├── db/                 # DuckDB + PostgreSQL 连接管理
│   │   ├── optimizer/          # 超参优化（Optuna）
│   │   ├── server/             # FastAPI 路由（ETF / 策略 / 回测 / 系统）
│   │   └── strategies/         # 策略插件（自动发现）
│   ├── tests/                  # pytest + pytest-cov（80%+ 覆盖率）
│   └── pyproject.toml
├── web/                        # Nuxt 4 前端
│   ├── app/
│   │   ├── components/         # Vue 组件（基于 @antfu/design）
│   │   ├── composables/        # useETFData / useStrategy / useBacktest / useMotion
│   │   ├── pages/              # 仪表盘 / 策略 / 信号 / 数据浏览 / 系统设置
│   │   └── types/              # TypeScript 接口定义
│   ├── tests/                  # Vitest + Playwright E2E
│   ├── nuxt.config.ts          # imports.autoImport: false
│   └── uno.config.ts           # 语义 Token 系统
├── docker/                     # Dockerfile + docker-compose
└── .github/workflows/          # CI（autofix + unit-test）
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
- **Ponytail**（后端）— 不到需要时不加功能，最短 diff，注释标记决策边界
- **双数据库** — DuckDB 做分析查询（列存），PostgreSQL 做事务持久化（行存）
- **双数据源** — Sina + 东方财富互备，单源故障不阻塞流程

## 已知限制

- 日线尚未启用前复权（种子流程使用 Sina 不复权数据）
- 行业 ETF 与宽基 ETF 共用同一套动量因子，申万行业指数数据源已接入但尚未集成到策略打分
- 分钟线数据已拉取但回测引擎仅支持日频

详见 [迭代方案](https://github.com/AbelTami/quant-fletch/blob/main/docs/迭代/README.md)。

## 开发

```bash
# 后端
cd api
uv sync --all-extras
uv run pytest                      # 运行全部测试
uv run pytest -m unit              # 仅单元测试

# 前端
cd web
pnpm i
pnpm dev                           # 开发服务器 :3000
pnpm test                          # Vitest 单元测试
pnpm build                         # 生产构建
```

## 许可证

MIT © [Quant Fletch](https://github.com/quantfletch)
