# 仓库全面分析工具（analysis）

对单个代码仓库执行**纯静态**全面分析（不运行目标仓库任何代码），产出 HTML 交互报告 + JSON 数据文件。需求定义见 [`REPO-ANALYSIS-REQ.md`](../REPO-ANALYSIS-REQ.md)，设计见 [`ANALYSIS-DESIGN.md`](../ANALYSIS-DESIGN.md)。

## 特性

- **11 章分析报告**：概述 / 结构 / 依赖 / 质量 / 安全 / 性能 / 文档 / 测试 / 架构 / **业务知识还原与接手就绪度**（含置信度 0–100%）/ 总结
- **异步增量**：15 个子任务后台串行流水线执行，发起即返回；Web 界面实时查看工作流、执行节奏与增量报告
- **混合执行**：确定性数据由工具采集（复用 audit 扫描产物 + lizard + OSV），架构/业务知识还原由 Claude Code headless（只读白名单）完成
- **健康度评分**：9 维度加权（安全/质量/业务知识各 15%…）→ A–F 等级
- **自包含归档**：单 HTML 文件（内联 ECharts/mermaid，离线可开）+ JSON（机器可解析，横向可比较）

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

# Web 可视化（按需启动、用完即退；退出不影响后台分析）
analysis/bin/analyze ui                     # http://127.0.0.1:8765

# 任务管理
analysis/bin/analyze status [task_id]       # 进度与子任务状态
analysis/bin/analyze history
analysis/bin/analyze cancel <task_id>
analysis/bin/analyze retry <task_id> [--subtask ai.summary]
analysis/bin/analyze report <task_id> --open
```

归档产物：`reports/<org>/<repo>/analysis/<timestamp>.{html,json}`（`latest.html` / `latest.json` 指向最近一次）。

## 开发

```bash
cd analysis && uv run pytest tests/ -q      # 单元测试
analysis/bin/analyze start <org>/<repo> --mock   # mock 联调（不跑真实采集/AI）
```

模块地图：`core/`（任务模型/存储/编排/daemon/评分/服务层）、`collectors/`（9 个确定性采集器 + audit 桥接）、`ai/`（claude headless 引擎 + 4 套 prompt/schema）、`web/`（FastAPI + 原生 JS 前端）、`reporters/`(归档 JSON/HTML)。

## 约束提醒

- 纯静态：覆盖率用静态代理指标或仓库已有产物；性能为静态启发式（报告含边界声明）
- 不分析贡献者等人员维度；git 历史仅用于仓库级信息与 commit 消息（业务还原）
- AI 子任务只读（Read/Grep/Glob 白名单），产物标注非确定性
- 联网查询/安装工具/MCP 使用前需与需求方确认（REQ §2.4）
