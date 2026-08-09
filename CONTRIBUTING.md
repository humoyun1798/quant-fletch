# 贡献指南

感谢你对 Quant-Fletch 的关注。

## 开发环境

### 后端 (Python)

```bash
cd api
uv sync --all-extras
uv run pytest
```

格式化与检查：

```bash
uv run black src/ tests/
uv run isort src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
```

### 前端 (Nuxt)

```bash
cd web
pnpm i
pnpm dev          # 开发服务器
pnpm test         # Vitest 单元测试
pnpm test:e2e     # Playwright E2E
pnpm lint         # ESLint
pnpm typecheck    # TypeScript 类型检查
```

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新增行业轮动策略
fix: 修复 RiskParity 波动率硬编码
refactor: 重构 FeatureService 参数化
test: 补齐 cleaner 复权测试
docs: 更新 API 文档
chore: 升级依赖
```

## 代码风格

- Python: black + isort + ruff + mypy (strict)，PEP 8
- TypeScript/Vue: `@antfu/eslint-config`，显式导入，单引号无分号尾逗号
- 不可变性：Python 用 `@dataclass(frozen=True)`，TypeScript 用展开运算符
- Ponytail（后端）：最小 diff，注释标记决策边界

## 添加新策略

1. 在 `api/src/strategies/` 下创建新文件（如 `sector_rotate.py`）
2. 继承 `BaseStrategy`，实现 `register()` 和 `score()` 方法
3. 文件放入目录后，`importlib` 自动发现——无需手动注册
4. 前端 `web/app/pages/strategy.vue` 的策略列表会自动拉取

## Issue 提交

欢迎提交：
- Bug 报告（请附带复现步骤和系统环境）
- 功能建议（请先搜索已有 Issue）
- 策略回测结果对比
- 数据质量问题

## PR 流程

1. Fork 仓库
2. 创建分支 (`git checkout -b feat/your-feature`)
3. 提交变更（遵循提交规范）
4. 确保测试通过
5. 提交 PR 到 `main` 分支

PR 会在 CI 流水线中自动运行 lint 和 test。
