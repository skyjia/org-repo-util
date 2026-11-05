# 仓库全面分析工具（analysis）

对单个代码仓库执行**纯静态**全面分析（不运行目标仓库任何代码），产出 HTML 交互报告 + JSON 数据文件。需求定义见 [`REPO-ANALYSIS-REQ.md`](../REPO-ANALYSIS-REQ.md)，设计见 [`ANALYSIS-DESIGN.md`](../ANALYSIS-DESIGN.md)。

## 特性

- **11 章分析报告**：概述 / 结构 / 依赖 / 质量 / 安全 / 性能 / 文档 / 测试 / 架构 / **业务知识还原与接手就绪度**（含置信度 0–100%）/ 总结
- **异步增量**：15 个子任务后台串行流水线执行，发起即返回；Web 界面实时查看工作流、执行节奏与增量报告
- **混合执行**：确定性数据由工具采集（复用 audit 扫描产物 + lizard + OSV），架构/业务知识还原由 Claude Code headless（只读白名单）完成
- **健康度评分**：9 维度加权（安全/质量/业务知识各 15%…）→ A–F 等级
- **自包含归档**：单 HTML 文件（内联 ECharts/mermaid，离线可开）+ JSON（机器可解析，横向可比较）
- **多语言覆盖**：Go / C# / TS / Vue / JS（经 audit）+ Python（ruff，含 bandit 安全规则）+ Shell（shellcheck）+ Dart/Flutter / Java / Ruby（manifest 解析、依赖图、测试与注释启发式）
- **策略守护**：fork 与 archived 仓库 `start` 预检拒绝（不产生任何任务）；生产代码 <100 行的文档/空仓库跳过 AI 出简版报告（零 AI 成本）

## 安装

```bash
bash analysis/setup.sh        # uv venv + 依赖
analysis/bin/analyze doctor   # 环境自检（git/gh/claude/vendor 资源）
```

依赖外部 CLI：`git`、`gh`（已认证，缺失时降级）、`claude`（Claude Code，AI 子任务）。

## 使用

```fish
# 发起分析（立即返回，后台执行；仓库须已克隆到 repos/<org>/<repo>）
analysis/bin/analyze start augmn/be-promotion-center
analysis/bin/analyze start augmn/fe-casamiel-admin --ref v1.2.0   # 指定分支/tag/commit
analysis/bin/analyze start augmn/ops-mdm --no-ai    # 只跑采集+评分+归档（零 AI 成本；AI 维度按缺失权重归一化）
analysis/bin/analyze start augmn/ops-mdm --ai-stub  # 全流程但 AI 走 schema-valid 桩（$0；报告不写 reports/）

# Web 可视化（按需启动、用完即退；退出不影响后台分析）
analysis/bin/analyze ui                     # http://127.0.0.1:8765

# 任务管理
analysis/bin/analyze status [task_id]       # 进度与子任务状态
analysis/bin/analyze history
analysis/bin/analyze cancel <task_id>       # 取消（flag 机制，子任务边界生效）
analysis/bin/analyze retry <task_id> [--subtask NAME]   # --subtask 默认级联重置下游
analysis/bin/analyze resume                 # 中断恢复（休眠/重启后自动续跑孤儿任务）
analysis/bin/analyze report <task_id> --open
```

> 注意：更新 analysis 代码后需重启 Web 进程（`pkill -f 'analyze ui'` 后重新 `analyze ui`）——
> 后端代码不热更新；页头显示版本号（v0.2.0+）可用于识别旧进程。

> 同理，**执行 daemon 也不热更新**：改动 `collectors/` 或 `core/` 后，已在跑的 daemon 仍用旧代码。
> 重启方式：`kill $(cat analysis/state/daemon.pid)`（daemon 空闲时安全）→ 删除
> `analysis/state/daemon.lock` / `daemon.pid` 残留文件 → 下一次 `analyze start` 会拉起新 daemon。

归档产物：`reports/<org>/<repo>/analysis/<timestamp>.{html,json}`（`latest.html` / `latest.json` 指向最近一次）。

## 开发

```bash
cd analysis && uv run pytest tests/ -q      # 单元测试
analysis/bin/analyze start <org>/<repo> --mock   # mock 联调（不跑真实采集/AI）
```

### 开发成本纪律（token 消耗同样要控住）

真实 AI 只在「prompt / schema 变更后」对小仓库抽检；其余场景按下列三档选一个，全部 $0：

| 场景 | 命令 | 覆盖 |
|------|------|------|
| 采集层 / 多语言回归 | `--no-ai` | 9 个采集器真实执行 + 评分归一化 + 归档（AI 子任务跳过） |
| 全流程编排 / 报告渲染 | `--ai-stub` | 采集器真实 + 4 个 AI 子任务返回 schema-valid 桩（prompt 仍完整渲染、桩产物过 jsonschema），报告只落 `state/tasks/<id>/report/` |
| 流水线联调（不关心数据） | `--mock` | 除 scoring/archive 外全部子任务 sleep 模拟 |

单任务 AI 成本硬上界：`config.MAX_TASK_AI_COST_USD`（默认 $5）——触顶后剩余 AI 子任务计划跳过并在报告标注，`analyze status` / `history` 显示累计成本。
桩产物文件在 `analysis/ai/stub_outputs/*.json`；改 schema 时同步改桩，`tests/test_dev_modes.py` 会先红。

模块地图：`core/`（任务模型/存储/编排/daemon/评分/服务层）、`collectors/`（9 个确定性采集器 + audit 桥接）、`ai/`（claude headless 引擎 + 4 套 prompt/schema）、`web/`（FastAPI + 原生 JS 前端）、`reporters/`(归档 JSON/HTML)。

## 约束提醒

- 纯静态：覆盖率用静态代理指标或仓库已有产物；性能为静态启发式（报告含边界声明）
- 不分析贡献者等人员维度；git 历史仅用于仓库级信息与 commit 消息（业务还原）
- AI 子任务只读（Read/Grep/Glob 白名单），产物标注非确定性
- 联网查询/安装工具/MCP 使用前需与需求方确认（REQ §2.4）
