# quant-fletch 项目备忘

A 股 ETF 量化轮动系统。后端 FastAPI(Python 3.14) + DuckDB + PostgreSQL，前端 Nuxt 4。

## 启动方式（Docker，已验证可用）

```bash
cd D:/桌面/etf/quant-fletch
docker compose -f docker/docker-compose.yml up -d
```

| 服务 | 容器名 | 宿主机端口 | 说明 |
|---|---|---|---|
| PostgreSQL | `quant-fletch-db-1` | 不对外暴露 | pgvector/pgvector:pg16 |
| FastAPI | `quant-fletch-api-1` | **18000** → 容器 8000 | 文档 <http://localhost:18000/docs> |
| Nuxt | `quant-fletch-nuxt-1` | **3000** | 界面 <http://localhost:3000> |

数据初始化：界面 `/setup` 页点按钮，或
`curl -X POST http://localhost:18000/api/v1/system/seed -H "Content-Type: application/json" -d '{"mode":"full"}'`

## 必须记住的硬约束

1. **compose 顶层必须有 `name: quant-fletch`**。本目录名叫 `docker`，若省略该字段，
   compose 项目名会变成 `docker`，与 `D:\桌面\社媒项目\docker` 项目**共用卷命名空间**，
   会挂载到对方同一个 `docker_pgdata`（实测导致 PG 认证失败）。
   **`docker_pgdata` 属社媒项目，绝不可删除。**
2. **宿主机端口不能随便选**。Windows 保留区间为 `5396-5495`、`7948-8047` 等
   （`netsh interface ipv4 show excludedportrange protocol=tcp` 可查），
   **5432 与 8000 都在保留区内**，Docker 绑定会报 access forbidden。
   现用 18000(API)、3000(前端)。
3. **前端依赖必须用 pnpm 9.15.9**。`pnpm-lock.yaml` 由 pnpm 9 生成，且仓库
   `pnpm-workspace.yaml` 里的 `trustPolicy: no-downgrade` 会被 pnpm 12 强制执行，
   从而拒绝锁文件中已存在的 `semver@6.3.1`。Dockerfile.web 里已固定该版本。
4. **`down -v` 会清掉本项目自己的数据卷**。项目名已固定为 `quant-fletch`，故
   `docker compose down -v` 只移除 `quant-fletch_pgdata` 与 `quant-fletch_duckdb_data`，
   **不再波及社媒项目的 `docker_pgdata`**（加 `name` 之后此前的担心已解除）。
   但删掉这两个卷 = 本项目数据全丢、必须重新 seed。因此：
   - 只是想停服务 → `docker compose -f docker/docker-compose.yml down`（**不加 `-v`**）
   - 想重置数据 → 才用 `-v`，之后要重新触发 seed
   另：早期遗留的孤儿卷 `docker_duckdb_data` 已不属本项目，未删除。
5. 宿主机上跑 `uv sync` 会失败：WorkBuddy 沙箱禁止删除文件
   （`SAFE_DELETE_FAIL_CLOSED`），在 `jsonpath` 打包收尾阶段中断。这是环境问题，
   与项目无关，Docker 内构建正常。
6. **回测区间默认值由后端按库中最新交易日决定**（`end_date` 省略即取
   `max(etf_daily.date)`，`start_date` 省略即取 2020-01-01）。
   **不要在任何地方写死回测日期** —— 原代码把 `end_date` 硬编码为 `'2025-12-31'`，
   导致界面与 API 都看不到更新的数据（用户实际报障过）。
7. **`adj_close` 曾是「不复权价」、含公司行为断层 —— 已修（前复权回补）。**
   A 股 ETF 有涨跌停，单日 |涨跌幅| 超过涨跌停必是份额折算/分红造成的价格断层。
   实测 `etf_daily` 曾有 **35 处断层、涉及 18/37 只 ETF**，其中 515880 通信ETF
   在 2026-02-03 的 -65.70% **直接导致回测净值当天暴跌 -35.26%**。
   根因：`clean_etf_data()` 在无 `adj_close_ref` 时令 `adj_close = close`，
   而东财 qfq 源在本机全局不可用（`ConnectionError`，CDN 屏蔽非浏览器 TLS），
   全部降级走 Sina 不复权价。
   **修法**：新增 `api/src/data/price_adjust.py` 做「断层检测 + 前复权回补」，
   并接入 `clean_etf_data()`（以后每次 seed 自动回补）。
   阈值**必须按标的涨跌停来定**：创业板/科创板 ETF 是 20%（登记在 `LIMIT_20PCT`），
   其余 10%；一律用 10% 会把 159915 真实的 ±20% 涨跌停误判为断层、反而破坏行情。
   存量数据用 `tools/qf_fix_adjustment.py` 就地修正（已执行：22 处 / 16618 行，
   复核剩余断层 0）。
   **前复权以最新价为锚，故最新日 `adj_close == close`，与实时行情同口径。**
8. **前端访问后端的地址是构建期注入的，改完必须重新 build nuxt。**
   - `API_BASE_URL`（`nuxt.config.ts` 的 `routeRules` 代理目标，SSR 侧用）
   - `VITE_WS_ORIGIN`（浏览器侧 WebSocket 直连地址，回测进度推送用）

   二者都只在 `nuxt build` 时求值，**在 compose 里设 runtime `environment` 无效**。
   配置位置：`docker/docker-compose.yml` 的 `nuxt.build.args`；
   `docker/Dockerfile.web` 中是带默认值的 `ARG`（默认内网直连
   `http://api:8000` / `ws://localhost:18000`）。
   **当前值：两个都指向内网穿透地址 `101.42.40.10:10004`
   （`API_BASE_URL=http://101.42.40.10:10004`、`VITE_WS_ORIGIN=ws://101.42.40.10:10004`）。**
   用户明确要求走隧道（2026-09-21 其重启 frpc 后再次确认）。

   ⚠️ **已知代价**：`API_BASE_URL` 是 **SSR 侧**的服务端请求，指向公网后
     每次 SSR 都要绕公网一圈，且**隧道一断、本地界面也会取不到数据**
     （2026-09-21 实际发生过一次）。想更稳就把 `API_BASE_URL` 单独改回
     `http://api:8000`，只让浏览器直连的 WebSocket 依赖隧道。
     **不要擅自改** —— 用户已知情并选择走隧道。

   `web/app/middleware/setup.global.ts` 已修：原先 fetch 失败一律跳 `/setup`，
   与"未初始化"混为一谈、会误导用户去点初始化按钮。现改为失败时放行
   （这样隧道再断也只是"没数据"，不会伪装成"初始化失败"）。

   **本机路径纠正**：`C:\Users\Administrator\Desktop` **不存在**，桌面实际在 `D:\桌面`。
   因此 `frp` 相关目录也不在 Desktop 下（frp-admin 曾部署在 `C:\frp-admin`，
   现该目录已不存在，位置由用户自行掌握）。

## 已知的仓库自身缺陷（未修，供后续迭代）

- `/api/v1/system/status` 在初始化进行中不返回进度：接口判断 `status == 'running'`，
  但 `data/seed/__init__.py` 写入的是 `'seeding'`，字符串不一致。
- **后端路由不合并参数默认值**：`routes/backtest.py` 用
  `params.get(pd_.name, pd_.default)` 校验后，却把**原始 `params`** 传给
  `strategy.warmup()`。而 6 个内置策略的 `warmup()` 普遍是 `params['x']` 直接取值
  → **API 调用时 `params` 留空或缺项即 `KeyError`、回测 failed**。
  界面表单会带全参数故不触发。绕过：从 `/api/v1/strategies` 取 `params[].default` 补全。
- `base.py` 的 `generate_signals()` 里 `turnover=0.0` 是写死的 →
  `metrics.avg_turnover` 与每期 `turnover` 恒为 0。
- `routes/etfs.py` 的分钟线聚合依赖 DuckDB 原生 `time_bucket`，非 TimescaleDB。
- 东方财富数据源在本机网络下常被 `RemoteDisconnected` 打断，会自动降级 Sina 源。
  （后果：本次 seed 后 `etf_daily.adj_close` 实为**不复权**价，分红除权日会产生假跌破。）
- README 声称「docker compose up 一条命令」不成立 —— 原始 compose/Dockerfile 有多处
  硬错误（详见 `2026-09-19.md`）。

## ⚠️ 回测引擎的两个确定性缺陷（已修，改任何策略前必读）

**症状**：同一策略同一参数，多次运行总收益在 **-17% ~ +89%** 之间乱跳。

1. **`_Portfolio.execute()` 会整笔丢弃买单**（严重）。原代码：

   ```python
   actual_cost = target_cost * scale
   if actual_cost > 0 and actual_cost <= self.cash:   # 临界判断后整笔丢弃
   ```

   缩放后各笔成本之和 ≈ 可用现金，末位浮点误差让最后一笔恰好超出而**被整笔丢弃**
   （丢的是整个仓位），且丢哪笔取决于买入顺序。→ 已改为
   `actual_cost = min(target_cost * scale, self.cash)` 截断而非丢弃。

2. **策略侧遍历 `set` 导致顺序不确定**。`for code in held:` 的迭代顺序由字符串哈希
   种子决定；卖出顺序会改变引擎里 `self.cash += ...` 的**浮点累加顺序**
   （浮点加法不满足结合律），末位差异一路传导到买入的 `available`/`scale`，
   最终触发上面的丢弃分支。→ 新策略已改 `sorted(held)`。
   **写新策略时，凡是会流入信号顺序的集合遍历都必须排序。**

另：polars 的 `group_by` **默认不保证输出行顺序**（实测同一数据连续 3 次返回 3 种顺序），
若分组结果顺序会传导到信号顺序，必须显式 `.sort(...)`。

验证手段（`tools/` 下已有脚本）：`qf_determinism.py`（同进程重复 5 次比净值指纹）、
`qf_engine_repro.py`（对照内置策略跨进程比指纹）。**新增策略后务必跑一次**，
跨 3 个容器指纹一致才算过关；`PYTHONHASHSEED=0` 可作为定位辅助。

## 本项目自有的 MA10 策略（新增）

`api/src/strategies/ma10_trend.py` → `MA10Trend`，`meta.name = 'MA10 趋势跟踪'`，
日频，被 importlib 自动发现（现共 **7** 个策略）。参数默认：
`ma_period=10, max_deviation=0.015, stop_factor=0.995, confirm_days=2,
cooldown_days=3, min_hold_days=2, slope_lookback=5, require_slope_up=1`。

编写约定（与框架的适配要点）：
- `filter_universe()` **不要过滤**，返回全池。引擎只按 signals 里的 sell 建仓，
  过滤掉跌破 MA 的标的后持仓永远收不到卖出信号、仓位会卡死。
- `register()` **不要声明引擎因子**。`FeatureService.resolve()` 按 `category` 分派，
  声明 `'momentum'` 会每个调仓日白算一次动量再 JOIN（用不到）。
- 入场**只对新标的发 buy**。对已持仓标的发 buy 会被引擎归一化成"把全部现金砸进去"。
- `warmup()` 一律 `params.get(k, default)`，规避后端不合并默认值。
- 引擎**无法保留现金**（`execute()` 归一化权重）→ "首仓 ≤40%" 表达不出来。
  使用者已确认仓位自行控制，故本策略只输出"该持有哪些"。

标的池当前为 **34 只**：原 30 只 + 用户自选补充 7 只 − 移除 3 只。

- 补充的 7 只（代码经 akshare 实测校验）：515220 煤炭ETF国泰、512800 银行ETF华宝、
  159865 养殖ETF国泰、512890 红利低波ETF华泰柏瑞、515050 通信ETF华夏、
  560860 工业有色ETF万家、159652 有色ETF汇添富。**只加 ETF，不加个股**
  （东瑞股份是股票，不在池内）。
- **已移除 3 只**（用户以「这两个行业是断层的」为由要求）：
  515880 通信ETF、515050 通信ETF华夏、512800 银行ETF华宝。
  随之清掉了它们的存量数据（日线 5608 行、分钟线 5910 行、PG 元数据 3 行），
  否则 seed「按 code 删了再写」的机制会让数据残留、回测照样交易。
  删除工具：`tools/qf_purge_codes.py`（**执行前须先 stop api 释放 DuckDB 锁**）。

**断层问题已根治**（不再需要靠移除标的规避）—— 见硬约束 7 的前复权回补。
先前移除的 515880/515050/512800 三只仍保持移除状态，**如需加回可直接加**
（数据会重新拉取，且现在 adj_close 会自动复权）。

**`etf_sector_map` / `sector_daily` 为空的问题已修**（三处 bug 叠加）：
1. akshare 函数名失效 —— 原 `ak.index_sw_level1_spot()` / `ak.index_sw_hist()`
   在当前版本**不存在**，正确为 `ak.sw_index_first_info()` 与
   `ak.index_hist_sw(symbol=..., period='day')`（symbol **不带 `.SI` 后缀**，
   返回**无涨跌幅列**、`日期` 为 Date 类型）。
2. `build_etf_sector_map()` 把 `verified` 恒写成 False，而 `sector_rotate.py`
   查询带 `WHERE verified = TRUE` → 永远查不到映射。
3. **最关键**：`sector_rotate.py` 的 `self._ddb = params.get('_ddb')` ——
   全项目**无任何调用方传 `_ddb`**，故恒为 None、整个行业分支是死代码。
   已改为未注入时自行打开 DuckDB 连接。

现已灌入 `sector_daily` **82728 行**（31 行业，2015-01-05 ~ 2026-09-18）、
`etf_sector_map` 15 行。工具：`tools/qf_init_sector_data.py`（**须先 stop api**）。

## ⚠️⚠️ 未修的结构性问题：5 个内置策略「只买不卖」

引擎**只在收到 `sell` 信号时卖出**（`self_loop.py`）。而 7 个内置策略中
**只有 `MA10 趋势跟踪` 与 `带止损动量增强` 会产生 sell**；
`双均线动量轮动` / `行业轮动` / `趋势+均线择时` / `多因子综合打分` /
`波动率加权风险平价` **完全没有卖出信号**。

后果：这些策略**只买不卖、持仓只增不减**，最终把池内标的几乎全买一遍，
**排名与选股逻辑形同虚设**（实证：`趋势+均线择时` 的 `ma_period` 从 200 改到 5，
344 个调仓日中 316 个选中的标的都不同，**净值指纹依然逐位相同**）。

**✅ 已修：引擎层「目标组合」模式**（用户选定方案 ①）
------------------------------------------------------------------
`StrategyMeta` 新增 `position_mode`（默认 `'incremental'`）：

- `'incremental'` —— `allocate()` 发增量指令，引擎不动它没提到的持仓。
  **`MA10 趋势跟踪` 必须用这个**（它只对新标的发 buy，一刀切会清空其存量仓位）。
- `'target'` —— `allocate()` 发当期目标组合，引擎自动卖出目标之外的持仓。
  已声明：`双均线动量轮动`、`行业轮动`、`趋势+均线择时`、`多因子综合打分`、
  `波动率加权风险平价`。

引擎侧实现在 `backtest/self_loop.py::_reconcile_target_portfolio()`。
三个要点：① 目标之外的持仓卖出；② 目标内且已持有的转 `hold`、**不再买入**
（引擎的 buy 按 `total_equity × 权重` 算目标成本、非增量，重复发 buy 会超配）；
③ 卖出列表必须**排序**（逐笔累加现金对顺序敏感）。
另修了 `generate_signals` 把 `sell` 也计入持仓的计数错误。

**⚠️ 写新策略时**：如果它是"每期持有一个 top-N 组合"，就声明
`position_mode='target'`，不要自己实现卖出。

## ⚠️ 另一个坑：因子参数曾恒为默认值（已修）

`base.py::_resolve_factors()` 原用 `getattr(self, 'params', None)` 取参数传给
`FeatureService.resolve()`，而基类 `warmup()` 里的 `self.params = params`
**从未执行** —— 7 个策略全部覆写了 `warmup()` 且都没调 `super().warmup()`。
于是 params 恒为 None，`factor_engine` 里 `params.get('lookback', 60)`
**永远取默认值 60**。这是「改 lookback 净值逐位不变」的真正底层原因。

**修法**：新增 `BaseStrategy._factor_params()` —— 优先用显式 `self.params`，
否则**按 `register()` 声明的 ParamDef 从实例属性回填**（warmup 存的就是
`self.<参数名>`）。一处修好，无需改动任何策略。

修复后实测 `lookback` 对双均线动量轮动的真实影响：
20 → **-4.40%**；60 → 25.16%；120 → **38.03%**（三个不同指纹）。
**写新策略时不要在 warmup 之外再存一份参数副本。**

## 已改动的文件（相对原始仓库）

- `docker/docker-compose.yml`：加 `name`；db 去掉 `cap_drop` 并加 tmpfs；api 加端口映射
  与 python 版 healthcheck；db 镜像换 pgvector/pgvector:pg16。
- `docker/Dockerfile.api`：补 COPY uv.lock；加 `--no-install-project`；
  用 `useradd` 替代 Alpine 的 `adduser`；加 `PYTHONPATH=/app/src`；
  预建并 chown `/app/data`。
- `docker/Dockerfile.web`：固定 pnpm 9.15.9（deps 与 builder 两个阶段）；
  构建期注入 `API_BASE_URL` 与 `VITE_WS_ORIGIN`。
- `web/nuxt.config.ts`：代理目标改为读 `process.env.API_BASE_URL`。
- `web/app/config/api.ts`：`WS_BASE` 支持构建期 `VITE_WS_ORIGIN` 注入。
- `web/app/middleware/setup.global.ts`：改用 `useRequestFetch()` 修复 SSR 重定向。
- `pnpm-lock.yaml`：补齐 `catalogs:` 缺失条目、对齐 importer specifier
  （仅元数据，版本号未动）。原文件备份为 `pnpm-lock.yaml.bak-20260919`。
- `api/src/backtest/self_loop.py`：修复买单被整笔丢弃的确定性缺陷（见上）。
- `api/src/strategies/ma10_trend.py`：新增 MA10 趋势跟踪策略。
- `api/src/data/seed/etf_config.py`：`ETF_POOL` 由 30 只 → 补 7 只 → 移 3 只 = **34 只**。
- `web/app/config/labels.ts`（新增）：界面文案中英映射层，含指标/动作/参数/选项/阶段
  五组映射。**以后改界面文案改这里，不要散落在各组件里**；后端字段名保持英文不动，
  仅在前端渲染时翻译。
- `web/app/components/*.vue`、`web/app/pages/*.vue`：12 个文件的中英文案替换
  （区块标题、表头、动作标签、运行按钮、图表图例、参数标签）。
  刻意保留 `Quant-Fletch`（产品名）/ `GitHub`（品牌）/ `ETF`（行业通用词）。
- `api/src/server/routes/backtest.py`：新增 `_latest_data_date()` / `_resolve_dates()`，
  三个端点（`/backtest`、`/backtest/compare`、`/backtest/optimize`）的默认日期由
  硬编码 `'2025-12-31'` 改为**库中最新交易日**。原实现导致界面与 API 都拿不到新数据。
- `web/app/types/backtest.ts`：`start_date` / `end_date` 改为可选。
- `web/app/pages/strategy.vue`：不再传死日期，交由后端解析默认区间。
- `api/src/strategies/multi_factor.py`：修复 `_correlation_penalty()` 空数组混入
  `np.column_stack` 导致的回测崩溃（见下）。
- `api/src/strategies/allocation.py`：`build_cov_from_prices()` 同款 bug，改为数据不全
  即返回 `None` 由调用方回落等权。
- `api/src/data/price_adjust.py`（**新增**）：价格断层检测 + 前复权回补。
  含 `LIMIT_20PCT`（20% 涨跌停标的登记表）。**新增创业板/科创板 ETF 时要补进去。**
- `api/src/data/cleaner.py`：`clean_etf_data()` 新增第 5 步 `_fix_price_gaps()`，
  每次 seed 自动回补断层。
- `api/src/data/sources/shenwan.py`：修复失效的 akshare 函数名
  （`sw_index_first_info` / `index_hist_sw`）、剥 `.SI` 后缀、自算 `change_pct`、
  日期比较改用 `_yyyymmdd()`、`verified` 改为 True、扩充 ETF→行业映射至 15 条。
- `api/src/strategies/sector_rotate.py`：修复 `_ddb` 从未被注入导致行业分支成为
  死代码（改为未注入时自行打开 DuckDB 连接）+ 新增 `teardown()` 释放连接。
- `api/src/strategies/base.py`：`StrategyMeta` 新增 `position_mode`（默认
  `incremental`）；新增 `_factor_params()` 修复因子参数恒为默认值的缺陷；
  `generate_signals()` 持仓计数改为 buy+hold。
- `api/src/backtest/self_loop.py`：新增 `_reconcile_target_portfolio()`，
  实现「目标组合」模式（当期目标之外的持仓自动卖出）。
- `api/src/strategies/{momentum_rotate,sector_rotate,trend_ma,multi_factor,
  risk_parity}.py`：声明 `position_mode='target'`。
  **`ma10_trend.py` 与 `stop_loss_momentum.py` 保持 `incremental`，不要改。**
- `tools/`：诊断/验证脚本（`qf_*.py`），非生产代码，可随时删除。
  - `qf_scan_i18n.py` 扫描界面英文残留
  - `qf_signal_probe.py` 跑回测并打印最近几期买卖信号
  - `qf_run_strategy.py` 直接跑任意/全部策略并逐一报告成败
    （**排查「某策略跑不通」首选**）
  - `qf_api_backtest.py` 经 HTTP API 跑回测（自动补全参数默认值）
  - `qf_scan_price_gaps.py` 扫描价格断层
  - `qf_fix_adjustment.py` 就地修正 `adj_close`（默认 dry-run，`--apply` 才写库）
  - `qf_purge_codes.py` 按代码清理存量数据（**须先 stop api**）
  - `qf_init_sector_data.py` 单独灌申万行业数据（**须先 stop api**）
  - `qf_check_latest.py` 核对数据是否已到最新交易日
  - `qf_robustness.py` 多窗口稳健性 + 年/月收益（容器内版）
  - `qf_monthly_report.py` **纯 HTTP 版**年度/月度报告（不依赖 Docker CLI）
  - `qf_sweep.py` / `qf_sweep_report.py` / `qf_final_check.py` 参数扫描三件套
  - `qf_mac_migration_guide.md` 迁到 Mac mini M4 的完整步骤

## ⚠️ 仓库状态：远端是旧版本，不能直接 clone（2026-09-24 核查）

`git status` 实测：**38 项未提交改动 + 6 个未跟踪新文件**，
且本地 `main` 与 `origin/main` **领先 0 个提交** ——
**GitHub 上的代码不含任何一轮修复**。

未跟踪但关键的文件：`api/src/strategies/ma10_trend.py`（**MA10 策略本身**）、
`api/src/data/price_adjust.py`、`web/app/config/labels.ts`、`tools/`。

**部署/迁移前必须先 `git add -A`（`-A` 不能省，否则新文件不进提交）+ commit + push，
或直接拷贝工作目录。** 详见 `tools/qf_mac_migration_guide.md`。

架构兼容性（已逐项实测，迁 ARM64 无障碍）：
`python:3.14-slim` / `node:22-alpine` / `pgvector/pgvector:pg16` 均含 arm64；
`uv.lock` 含 109 条 aarch64；`pnpm-lock` 里 rollup/esbuild/lightningcss 的 linux-arm64 都在；
`.dockerignore` 已排除 `node_modules`；Dockerfile 与 compose **全是 LF 行尾**，无 CRLF 问题。

迁移时必改：`docker-compose.yml` 里 `nuxt.build.args` 的
`API_BASE_URL` / `VITE_WS_ORIGIN`（当前指向 **Windows 的 frp 隧道**，Mac 上要改回内网）；
`.env` 被 gitignore、clone 不带，需在目标机重建。

## ⚠️ 环境故障记录：Docker CLI 静默失效（2026-09-21 凌晨）

**现象**：`docker ps` / `docker version` / `docker run` 全部**退出码 1、零输出**
（连同一 shell 命令里的 `echo` 都不输出，极具误导性，容易误判成脚本问题）。
`docker.exe` 真二进制直接调用同样失败；非沙箱模式、PowerShell 通道都不行。
**但容器仍在正常运行** —— `curl localhost:18000/health` 返回 200。

**判断**：Docker CLI 与守护进程的连接断了（Docker Desktop 引擎异常），
**需手动重启 Docker Desktop**。

**绕过办法（已验证）**：分析脚本不要绑死在临时容器上。改为**通过 REST API 跑回测**
（`POST /api/v1/backtest` → 轮询状态 → `GET /api/v1/backtest/{id}` 取 `equity_curve`，
其中含 `equity` 与 `benchmark` 两个字段），宿主机 Python 处理即可 ——
见 `tools/qf_monthly_report.py`。只要 api 容器活着就能完整跑通。

**其他踩坑**：
- 长任务一律 `python -u`：Python 管道输出是块缓冲，进程中断则日志为 0 字节。
- 容器内 `/tmp` 会随 `--rm` 销毁：报告写挂载目录，或同时打到 stdout 兜底。
- 区间收益的首个区间要以**初始资金**为基数，否则第一年算出 NaN。
- 基准净值要取 `pt['benchmark']`，不能拿策略净值凑。

**回测结论：没有一个是稳健的。** 7 个策略在多窗口下跑赢基准的最佳成绩仅 **3/6**；
且 **2026 年至今集体跑输**（基准 -1.0%，各策略 -15%~-23%）。
它们呈典型**低 beta 防守型**：基准跌时抗跌（2022/2023），基准大涨时跟不上（2024），
绝对收益几乎全靠 2025 一年。**引用任何策略的历史收益前，先看
`tools/qf_monthly_report.md`。**

## ⚠️ 写策略时的三个高频踩坑（都已修，但别重犯）

1. **`np.column_stack` 前必须剔除空序列**。`multi_factor.py` 与 `allocation.py` 里
   都曾出现「把空数组也塞进列表，而 `min_len` 又跳过空数组计算」的写法，
   空数组切片后长度仍为 0 → `ValueError: array at index N has size 0`。
   **触发条件：回测起点早于部分 ETF 的上市日** —— 池内 8 只 ETF 首个交易日晚于
   2019-01-01（最早的芯片ETF 159995 是 2020-02-10），而 `get_price_df()` 会从
   `start_date` 再前推 365 天缓冲，故 2020-01-01 起的回测在首个调仓日必现。

2. **排序选股必须给并列排名一个确定性次级键**。
   `sector_rotate.py` 的 `allocate()` 原为
   `sorted(scores.items(), key=lambda x: x[1], reverse=True)` —— `sorted` 是稳定排序，
   **并列时名次由 dict 插入顺序决定**，而插入顺序来自 polars `group_by`（不保证顺序）
   与 DuckDB 无序扫描。`sector_weight=1.0` 时同行业 ETF 得分完全相同、并列极多，
   于是**同一组参数连续三次跑出 +169.31% / +150.74% / +117.19%**。
   修法：排序键写成 `lambda x: (-x[1], x[0])`（以 code 打破并列），
   DuckDB 查询补 `ORDER BY`，polars 聚合后补 `.sort()`。
   **凡是分数可能并列的选股逻辑都要照此处理。**

3. **长任务与临时容器**：脚本一律 `python -u`（管道输出是块缓冲，中断则日志为空）；
   报告写挂载目录而非容器内 `/tmp`；并行 worker **各用独立的 duckdb 副本**
   （DuckDB 独占锁，共用同一文件时只有先抢到的能跑）；
   bash 重定向必须写**宿主机路径**（写成 `/data/x.log` 是容器内路径，会静默失败）。

## 参数调优结果（2026-09-21，已写入默认值）

判定「最优」必须同时满足：收益提升 + **邻域是平台而非尖峰** + 结果可复现。

**已改默认值**（4 个）：
- `MA10 趋势跟踪`：`max_deviation` 0.015 → **0.01**（53.5% → 101%）
- `行业轮动`：`top_n` 5 → **3**、`sector_weight` 0.7 → **1.0**（25.5% → 180%）
- `趋势+均线择时`：`top_n` 5 → **3**、`ma_period` 200 → **60**（7.9% → 42%）
- `多因子综合打分`：`lookback` 60 → **20**、`top_n` 5 → **8**（37.4% → 65%）

**拒绝改默认值的 3 个**（最优点是尖峰 = 过拟合）：
`双均线动量轮动`（lookback 60 是尖峰）、`波动率加权风险平价`（120 是尖峰）、
`带止损动量增强`（120 是尖峰，且原默认最稳：6/7 年正收益、回撤 -21.0% 最佳）。

⚠️ **全部是 in-sample 最优，实盘必然衰减**；且 2026 年至今仍全线为负
（-10.6%~-21.9%，基准仅 -1.0%）。**真正的样本外验证（2020-2023 选参、
2024-2026 检验）尚未做** —— 引用这些收益数字时必须说明这一点。

参数扫描工具：`tools/qf_sweep.py`（含逐年收益）、`qf_sweep_report.py`（汇总）、
`qf_final_check.py`（推荐 vs 默认各跑两遍验证可复现，**下参数结论前必过这关**）。
