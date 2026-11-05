# 仓库全面分析工具 — 实现设计文档

> **对应需求**：`REPO-ANALYSIS-REQ.md` v5（需求章节号以 `REQ §x.x` 引用）
> **状态**：设计稿 v1（2026-11-05）
> **模式**：AI 驱动开发，任务清单见 `ANALYSIS-DEV-PLAN.md`

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                              │
│   analyze CLI（独立 Python CLI）      Web 应用（按需启动）        │
│   start/status/history/cancel/retry   任务列表·工作流·事件流·预览   │
└──────────────┬──────────────────────────────┬───────────────┘
               │ 写任务队列                     │ 读状态/事件/数据（SSE）
┌──────────────▼──────────────────────────────▼───────────────┐
│                    状态存储层（文件，无数据库）                    │
│   analysis/state/tasks/<task_id>/                            │
│   ├── task.json        任务与子任务状态（唯一事实源）              │
│   ├── events.jsonl     追加式事件流（Web 实时节奏的数据源）         │
│   ├── collected/*.json 确定性采集产物（增量落盘）                  │
│   ├── ai/*.json        AI 子任务产物                           │
│   └── daemon.log       执行器日志                              │
└──────────────▲──────────────────────────────────────────────┘
               │ 轮询队列·串行执行·增量写入
┌──────────────┴──────────────────────────────────────────────┐
│              执行器 Daemon（独立后台进程，与 Web 解耦）             │
│   Orchestrator：DAG 拓扑排序 → 子任务状态机 → 超时/重试            │
│   ├── Collectors（确定性采集，8+1 个）                          │
│   │     overview/structure/dependencies/quality/security/     │
│   │     performance/docs/tests/git_context                    │
│   │     └── AuditBridge（复用 audit lint/安全产物，REQ §1.3）    │
│   ├── AI Engine（claude -p headless，只读白名单）                │
│   │     ai.architecture / ai.business_knowledge /             │
│   │     ai.conclusions / ai.summary                           │
│   ├── Scoring（规则评分 ×7 + AI 评分 ×2 → 加权 → A–F）           │
│   └── Reporters（归档 JSON + 自包含 HTML）                       │
└─────────────────────────────────────────────────────────────┘
```

**关键数据流**：CLI `start` 创建 queued 任务并确保 daemon 存活 → daemon 按 FIFO 取任务 → 按 DAG 串行执行子任务 → 每个子任务完成即写 `collected/`或`ai/` 产物 + 更新 `task.json` + 追加 `events.jsonl`（此即 REQ §4.1「增量落盘」）→ 全部完成后 scoring → 归档报告写入 `reports/<org>/<repo>/analysis/` → Web 端通过 SSE tail 事件流实时展示节奏，通过 preview API 渲染增量报告。

## 2. 目录结构

```
analysis/                          # 与 audit/ 并列；顶层目录即 Python 包（沿用 audit 布局）
├── __init__.py                    # import analysis.core.xxx（sys.path=项目根）
├── bin/analyze                    # CLI 入口（Click，参照 audit/bin/audit 模式）
├── pyproject.toml                 # uv 管理，Python 3.11
├── requirements.txt
├── setup.sh                       # uv venv + 依赖安装（参照 audit/setup.sh）
├── core/
│   ├── config.py                  # 路径常量、默认配置（超时、权重、端口）
│   ├── models.py                  # Task/Subtask dataclass + 状态枚举
│   ├── store.py                   # TaskStore：task.json/events.jsonl 原子读写
│   ├── registry.py                # 子任务注册表（名称→handler/依赖/类型/超时）
│   ├── orchestrator.py            # DAG 调度、状态机、超时/重试/取消
│   ├── daemon.py                  # 后台进程：pid 管理、队列轮询、空闲退出
│   └── scoring.py                 # 规则评分 ×7 + AI 评分接入 + 加权 + 等级
├── collectors/
│   ├── base.py                    # Collector 基类（统一输出契约）
│   ├── overview.py                # REQ §3.1  gh api + git
│   ├── structure.py               # REQ §3.2  行数/目录（纯 Python）
│   ├── git_context.py             # commit 消息摘要（供 AI 还原，去作者信息）
│   ├── dependencies.py            # REQ §3.3  manifest 解析 + 依赖图
│   ├── quality.py                 # REQ §3.4  AuditBridge(lint) + lizard 复杂度
│   ├── security.py                # REQ §3.5  AuditBridge(安全) + OSV + 启发式
│   ├── performance.py             # REQ §3.6  静态反模式启发式
│   ├── docs.py                    # REQ §3.7  文档清点 + 注释统计
│   ├── tests.py                   # REQ §3.8  测试清点 + CI 配置读取
│   └── audit_bridge.py            # 读取 reports/<org>/<repo>/latest/report.json
├── ai/
│   ├── engine.py                  # claude -p 封装：调用/超时/JSON 提取/校验/重试
│   ├── tasks.py                   # AI 子任务 handler（渲染 prompt→调 engine→校验落盘）
│   ├── prompts/                   # Jinja2 提示词模板（architecture/business_knowledge/conclusions/summary）
│   └── schemas/                   # AI 输出 JSON Schema（jsonschema 校验）
├── web/
│   ├── app.py                     # FastAPI 应用 + uvicorn 启动（仅 127.0.0.1）
│   ├── api.py                     # REST + SSE 路由
│   └── static/                    # 前端资源（全部本地化，REQ §4.3）
│       ├── index.html / app.js / style.css
│       └── vendor/                # echarts.min.js, mermaid.min.js（下载一次入库）
├── reporters/
│   ├── json_report.py             # 归档 JSON 组装（schema v1）
│   ├── html_report.py             # Jinja2 渲染自包含 HTML
│   └── templates/report.html.j2
├── state/                         # 运行时状态（gitignored）
└── tests/
```

## 3. 任务模型与子任务 DAG

### 3.1 子任务清单（15 个）

| 子任务 | 类型 | 依赖 | 超时 | 产出 |
|--------|------|------|------|------|
| `collect.overview` | det | — | 5min | `collected/overview.json`（REQ §3.1） |
| `collect.structure` | det | — | 5min | `collected/structure.json`（REQ §3.2） |
| `collect.git_context` | det | — | 5min | `collected/git_context.json`（commit 消息摘要、首末 commit、分支/tag，**不含作者信息**，REQ §1.2） |
| `collect.dependencies` | det | structure | 5min | `collected/dependencies.json`（REQ §3.3） |
| `collect.quality` | det | structure | 5min | `collected/quality.json`（REQ §3.4） |
| `collect.security` | det | dependencies | 5min | `collected/security.json`（REQ §3.5） |
| `collect.performance` | det | structure | 5min | `collected/performance.json`（REQ §3.6） |
| `collect.docs` | det | structure | 5min | `collected/docs.json`（REQ §3.7） |
| `collect.tests` | det | structure | 5min | `collected/tests.json`（REQ §3.8） |
| `ai.architecture` | ai | structure, dependencies, git_context | 30min | `ai/architecture.json`（REQ §3.9） |
| `ai.business_knowledge` | ai | structure, git_context, docs | 30min | `ai/business_knowledge.json`（REQ §3.10） |
| `ai.conclusions` | ai | 全部 8 个 collect.*（除 git_context） | 30min | `ai/conclusions.json`（各维度结论与改进建议，REQ §4.4） |
| `scoring` | det | ai.architecture, ai.business_knowledge | 1min | `collected/scoring.json`（REQ §3.11 评分） |
| `ai.summary` | ai | scoring, ai.conclusions | 30min | `ai/summary.json`（执行摘要 + 问题清单 + 路线图，REQ §3.11） |
| `report.archive` | det | 全部 | 2min | 归档 `reports/<org>/<repo>/analysis/<ts>.{html,json}` |

超时默认值即 REQ 第 7 章已决策值（确定性 5min / AI 30min），`config.py` 可配置。全局串行（REQ §4.1）：按拓扑序逐个执行，不做并行。

### 3.2 状态机

```
子任务: queued → running → completed
                     ├──→ failed(超时/异常/校验失败) → running(自动重试1次) → failed(终态,跳过)
任务:   queued → running → completed | failed | canceled
```

- 子任务失败重试 1 次（REQ 第 7 章）；仍失败 → 标记 failed、写事件、**无依赖关系的后续子任务继续**；依赖它的下游子任务标记 `skipped`（原因=上游失败）；
- `ai.summary` / `report.archive` 特殊：即使部分上游 failed/skipped 仍执行（报告需呈现失败状态，REQ 第 7 章容错）；
- 取消：CLI 向 `task.json` 写 `cancel_requested=true`，orchestrator 在每个子任务边界检查并终止（running 中的子进程被 kill）；
- 幂等重入：retry 时将 failed/skipped 子任务重置为 queued、任务状态回 queued 重新入队；orchestrator 跳过已 completed 的子任务。

### 3.3 task.json（状态唯一事实源）

```jsonc
{
  "schema_version": "1.0",
  "task_id": "20261105_143022-fe-casamiel-admin",
  "org": "augmn", "repo": "fe-casamiel-admin",
  "repo_path": "repos/augmn/fe-casamiel-admin",
  "ref": "main",                    // 用户指定，默认主分支（REQ §2.1）
  "commit_sha": "abc1234...",       // 解析后的实际基线，报告标注
  "status": "running",
  "cancel_requested": false,
  "created_at": "...", "started_at": "...", "finished_at": null,
  "duration_seconds": null,
  "progress": {"total": 15, "completed": 3, "failed": 0, "skipped": 0},
  "subtasks": {
    "collect.overview": {
      "status": "completed", "type": "det",
      "started_at": "...", "finished_at": "...", "duration_seconds": 12.3,
      "attempts": 1, "error": null, "output_file": "collected/overview.json"
    }
  },
  "report": {"html": null, "json": null}   // 归档后填路径
}
```

写入采用**原子替换**（tmp + rename），避免 Web 读到半截 JSON。

### 3.4 events.jsonl（执行节奏数据源）

```jsonc
{"seq": 1, "ts": "...", "type": "task_started", "message": "开始分析 augmn/fe-casamiel-admin@main"}
{"seq": 2, "ts": "...", "type": "subtask_started", "subtask": "collect.overview"}
{"seq": 3, "ts": "...", "type": "log", "subtask": "collect.overview", "message": "gh api 获取仓库元数据"}
{"seq": 4, "ts": "...", "type": "subtask_completed", "subtask": "collect.overview", "duration_seconds": 12.3}
// type: task_queued|task_started|subtask_started|subtask_completed|subtask_failed|
//       subtask_retry|subtask_skipped|log|task_completed|task_failed|task_canceled
```

追加写 + 单调 `seq`；Web SSE 按 seq 增量推送。

## 4. 执行器 Daemon

- **进程模型**：`analyze start` 创建任务后调用 `ensure_daemon()`——检查 `state/daemon.pid`（存在且进程存活则复用），否则 `subprocess.Popen([sys.executable, analyze, "_daemon"], start_new_session=True)` 拉起 detached 后台进程，stdout/stderr 重定向到 `state/daemon.log`；启动时以 **flock 独占锁**（`state/daemon.lock`）防双 daemon 竞态；
- **daemon 主循环**：每 1s 轮询 `state/tasks/*/task.json` 中 `status=queued` 的任务，按 `created_at` FIFO 取一个执行（全局串行）；**每 10s 写心跳** `state/daemon.heartbeat`（pid/时间戳/当前任务）；空闲超过 `daemon_idle_ttl`（默认 30min）自动退出（下次 start 重新拉起）；
- **Web 解耦**（REQ §4.3/第 7 章）：daemon 不依赖 Web 进程；Web 退出/未启动不影响执行；
- **中断恢复（自动续跑）**：daemon 启动时扫描 `status=running` 的孤儿任务（旧 daemon 已死，由 pid/flock 保证判定安全）→ 被中断的子任务重置为 `queued`（attempts 归零——中断非业务失败）→ **任务自动重新入队续跑**，无需人工 retry；已完成子任务靠幂等重入跳过；`cancel_requested` 意图保留；写「中断恢复」事件；
- **恢复触发点**：`start` / `retry` / `resume`（显式命令）/ `ui`（启动 Web 时）均执行 `ensure_daemon` → daemon 启动即恢复扫描；覆盖休眠唤醒（进程未被杀则冻结后继续执行，网络类子任务失败由退避重试兜底）与系统重启（下次任意命令触发恢复）两类场景；
- **重试退避**：子任务失败重试前等待（det 5s / AI 30s，`config.py` 可配），退避期间每秒检查取消请求；
- **已知局限**：宿主机休眠期间 SIGALRM 时钟语义不可靠，唤醒后子任务可能被立即判超时——由「自动重试 + 孤儿续跑」双层兜底，最坏情况该子任务多执行一次（幂等产物覆盖写，无副作用）。

## 5. 采集器设计（确定性）

统一契约：`Collector.collect(ctx) -> dict`，ctx 含 repo_path/org/repo/commit_sha/state_dir；输出 JSON 均含 `_meta: {subtask, generated_at, commit_sha, tool_versions, warnings[]}`；任何「如有」项缺失时按 REQ §2.3 输出 `{"found": false, "suggestion": "..."}` 结构而非省略字段。

| 采集器 | 实现要点 | 外部工具与降级 |
|--------|----------|----------------|
| overview | `gh api repos/{org}/{repo}`（subprocess）+ git 首末 commit / 分支 / tag；API 失败→降级纯 git 并标注「元数据未获取」（REQ 第 7 章） | gh（已认证）；降级：git |
| structure | 纯 Python 遍历统计：按扩展名→语言映射，区分生产/测试/生成代码；默认排除 `node_modules vendor dist build .git *.min.js *.lock coverage` 等，排除规则写入 `_meta` | 无 |
| git_context | `git log --pretty=%s%x09%ad`（**不取作者**）近 500 条 + 首次 commit + tag 列表；供 AI 还原业务演进 | git |
| dependencies | manifest 解析：package.json(+lock)/go.mod/*.csproj/requirements.txt/pyproject.toml；依赖图：JS→madge（若 node 可用）、Go→`go mod graph`、C#→csproj ProjectReference 解析、Python→import 正则解析；图输出为 nodes/edges JSON（前端/归档渲染） | madge/go 可选；缺失→按 REQ §3.3 标注省略原因 |
| quality | AuditBridge 取 lint issues（dimension=code_style）+ lizard 复杂度（圈复杂度/函数长度/NLOC）+ 超长文件 TOP N + 嵌套深度启发式 | lizard（pip）；audit 产物缺失→按 REQ §1.3 标注 |
| security | AuditBridge 取安全 issues + OSV batch API（`api.osv.dev/v1/querybatch`，用 manifest 精确版本查询，纯 HTTP 不执行代码）+ 危险模式启发式（eval/exec/innerHTML/SQL 拼接/硬编码危险函数，多语言正则库） | requests；OSV 不可达→标注降级 |
| performance | 静态反模式规则库（REQ §3.6）：循环内 DB/IO 调用（AST/正则上下文）、async 上下文 sync IO、大对象循环创建等；每条命中含文件/行号/证据片段；输出必须带边界声明字段 | 无（纯 Python） |
| docs | README 章节检查（快速开始/安装/配置标题模式）+ docs/ CHANGELOG CONTRIBUTING 清点 + 注释率（语言感知注释符）+ 公共 API 文档注释比例（JS export/Go 导出符号/C# public+///）+ OpenAPI/Swagger 文件探测 | 无 |
| tests | 测试文件识别（`*_test.go`、`*.test.js|*.spec.js|__tests__/`、`*Tests/*.cs` xunit 特征）+ 框架识别（deps 特征）+ 测试/生产代码比 + 空测试/无断言启发式 + `.github/workflows/*.yml` 中 test 步骤关键词读取（仅读文件）+ 覆盖率产物探测（lcov.info/coverage.xml/cover.out） | 无 |

**AuditBridge**（`audit_bridge.py`）：读 `reports/<org>/<repo>/latest/report.json`（audit 产物，结构 `{metadata, results[{repo, language, analyzer, issues[{file,line,column,severity,message,rule,tool,dimension,suggestion}], files_scanned, lines_scanned, duration_seconds}]}`）；按 `dimension` 分流到 quality/security；输出附 `audit_generated_at` 与 audit 时 commit（如产物中可得），与本次基线不一致时标注「结果可能过期」（REQ §1.3）；latest 不存在或语言未覆盖 → `{"found": false, ...}`。

## 6. AI 引擎设计

### 6.1 调用契约（claude headless）

```python
cmd = [
  "claude", "-p",                       # headless，prompt 走 stdin
  "--output-format", "json",            # 结构化返回 {result: "..."}
  "--allowedTools", "Read,Grep,Glob",   # 只读白名单：可看代码，不可写/不可执行
  "--max-turns", "60",
]
subprocess.run(cmd, input=prompt_text, cwd=repo_path, timeout=1800)
```

- **安全边界**：只读工具白名单；不给 Bash/Write/Edit——git 历史等上下文由 `collect.git_context` 预先采集注入 prompt，AI 无需执行命令（比开放 `Bash(git …)` 更收敛）；
- cwd = 目标仓库根，AI 用 Read/Grep/Glob 自行查证代码证据（REQ §4.4「AI 只解读不编造数据，引用证据来源」）；
- 返回解析：`result` 文本 → 提取首个 ```json 代码块（或整体 json.loads）→ `jsonschema` 校验对应 schema → 校验失败视为子任务失败（走重试）；
- prompt 中注入的采集数据做**体积裁剪**（TOP N 截断 + 摘要），控制上下文规模；
- 每个 AI 产物 JSON 均含 `_ai_meta: {model_hint, prompt_version, generated_at, nondeterministic: true}`——归档报告据此标注非确定性（REQ §4.4）。

### 6.2 四个 AI 子任务与输出 schema（要点）

| 子任务 | 输入（注入数据） | 输出 schema 关键字段 |
|--------|------------------|----------------------|
| `ai.architecture` | structure + dependencies（含图）+ git_context 摘要 | `overview, layers[], components[{name,responsibility,evidence}], patterns[{name,evidence,fit}], issues[{severity,title,detail,evidence,suggestion}], architecture_diagram_mermaid, doc_assessment, score(0-100), score_reasons[]` |
| `ai.business_knowledge` | structure + git_context + docs 采集结果；prompt 内嵌 REQ 第 6 章置信度分级标准全文 | `knowledge[{category,summary,evidence[],confidence(0-100)}], gaps[{topic,impact,suggestion,carrier}], contradictions[{type,description,evidence[],severity}], readiness{completeness,accuracy,consistency(各0-100),overall,conclusion}, score(0-100)` |
| `ai.conclusions` | 全部 collected/*.json 摘要 | `dimensions{structure,dependencies,quality,security,performance,docs,tests: {summary, findings[{severity,title,detail,evidence,suggestion}], suggestions[]}}` |
| `ai.summary` | scoring.json + conclusions + architecture + business_knowledge | `executive_summary(3-5句), top_issues[{priority(P0/P1/P2),title,detail,dimension}], roadmap{short[],mid[],long[]}, future_suggestions[]` |

Prompt 模板存 `ai/prompts/*.md.j2`（带 `prompt_version`），模板头部统一声明：角色、纯静态约束、证据引用要求、严格 JSON 输出、中文撰写。

## 7. 评分模型（REQ §3.11 已决策权重）

`scoring.py`：9 维度各 0–100 → 加权（安全 15/质量 15/业务知识 15/测试 12/架构 12/文档 10/依赖 9/结构 6/性能 6）→ 总分 → A≥90/B≥75/C≥60/D≥40/F。

- **规则评分 ×7**（structure/dependencies/quality/security/performance/docs/tests）：基线分 + 加减分项（密度类指标按 KLOC 归一），每项因子写入 `factors[]`（可解释、报告展示扣分原因）；
  - 示例 quality：`100 - min(40, high_issues/kloc×4) - min(25, complex_fn_ratio×50) - min(15, long_file_ratio×30)`；
  - 示例 security：critical 漏洞每个 -20（封顶 -60），high -8，中低递减；静态危险模式按密度扣分；
  - 数据缺失维度（如 audit 未覆盖且启发式无产出）→ 该维度标记 `score=null, reason`，加权时按剩余维度权重归一化重算并在报告标注；
- **AI 评分 ×2**：architecture.score、business_knowledge.score（readiness 三项按 0.4/0.3/0.3 合成），AI 输出须附 `score_reasons[]`；
- AI 子任务 failed 时对应维度 score=null，同上归一化处理。

## 8. CLI 设计（独立 Python CLI，REQ §4.2 已决策）

```fish
analyze start <org>/<repo> [--ref BRANCH_TAG_COMMIT]   # 立即返回 task_id；自动确保 daemon
analyze status [task_id]                                # 无参=当前/最近任务；进度+子任务表（rich）
analyze history [--limit N]                             # 历史任务列表
analyze cancel <task_id>
analyze retry <task_id> [--subtask NAME]                # 重置 failed/skipped，重新入队
analyze ui [--port 8765] [--no-browser]                 # 按需拉起 Web（前台，ctrl-c 退出）
analyze report <task_id> [--open]                       # 归档报告路径/打开
analyze doctor                                          # 环境自检：claude/gh/git/依赖/daemon 状态
analyze _daemon                                         # 内部命令：daemon 主循环（不对外文档化）
```

入口 `analysis/bin/analyze` 与 `audit/bin/audit` 同模式（sys.path 注入项目根 + Click）。

## 9. Web 应用设计（REQ §4.3）

### 9.1 API

| 端点 | 说明 |
|------|------|
| `GET /api/tasks` | 任务列表（含进度摘要） |
| `GET /api/tasks/{id}` | task.json 全量（子任务状态/耗时） |
| `GET /api/tasks/{id}/events?since_seq=N` | 事件增量拉取（轮询兜底） |
| `GET /api/tasks/{id}/stream` | **SSE**：tail events.jsonl 实时推送执行节奏 |
| `GET /api/tasks/{id}/preview` | 增量报告数据：组装 completed 子任务产物 + 未完成子任务状态占位 |
| `GET /api/tasks/{id}/report` | 归档报告元信息；`/reports/...` 静态 serve 归档 HTML |
| `POST /api/tasks` | 发起分析 {org, repo, ref}（与 CLI start 同逻辑） |
| `POST /api/tasks/{id}/cancel` / `retry` | 任务控制 |

FastAPI + uvicorn，仅绑定 127.0.0.1；`analyze ui` 前台运行、退出即停（Web 退出不影响 daemon，REQ §4.3）。

### 9.2 前端（原生 JS，无构建链，资源全本地化）

单页三视图：

1. **任务列表**：卡片式，状态徽章、进度条、耗时；「发起分析」表单（org/repo/ref）；
2. **任务详情——工作流视图**：子任务流水线图（按 DAG 拓扑排布，SVG 连线 + 状态色：灰=排队/蓝脉冲=执行中/绿=完成/红=失败/黄=跳过），节点显示耗时与重试次数；点击节点看产物摘要；
3. **任务详情——执行节奏 + 增量预览**：左侧事件流（SSE 实时滚动，含 AI 调用/重试/错误），右侧增量报告预览（完成维度渲染关键数据，未完成维度显示状态占位；手动/自动刷新，REQ §4.3「刷新即更新」）。

## 10. 归档报告生成（REQ 第 5 章）

- **路径**：`reports/<org>/<repo>/analysis/<timestamp>.html` + `<timestamp>.json`；更新符号链接 `latest.html`/`latest.json`（沿用 audit 的 symlink 模式）；
- **JSON**：`json_report.py` 组装——`{schema_version, metadata{org,repo,commit_sha,ref,analyzed_at,generator{version,prompt_versions},data_sources[],limitations[]}, scores{dimensions{9维:{score,weight,factors|score_reasons}},total,grade}, dimensions{11章内容}, issues[](汇总,含severity/priority/dimension/location), knowledge{list,gaps,contradictions,readiness}, subtasks_status}`；即待决策项 #1 的 schema v1 落定；
- **HTML**：Jinja2 单模板渲染为**自包含单文件**——数据以 `<script type="application/json" id="report-data">` 内嵌；`echarts.min.js` 与 `mermaid.min.js` 从 `web/static/vendor/` 内联；交互：侧边目录、章节折叠、图表 hover、问题清单按 severity/priority 筛选、置信度 badge（REQ §5.2）；
- **图表**：统计图（语言构成/复杂度分布/趋势等）用 ECharts 渲染 SVG；架构图/依赖图用内嵌 mermaid 源码由 mermaid.js **在浏览器渲染为 SVG**；
  - ⚠️ 与 REQ §5.2「预渲染为 SVG 后嵌入」的措辞偏差：改为浏览器端渲染 SVG。理由：mermaid-cli 预渲染需 puppeteer+Chromium（数百 MB、脆弱），违背轻量自包含原则；浏览器渲染最终产物同为矢量 SVG，视觉与清晰度等效。已在决策记录 D6 备案；
- 头部标注区：分析时间、commit SHA、数据来源清单、纯静态局限声明、audit 产物时间、AI 非确定性标注（REQ §5.2）。

## 11. 技术选型与依赖

| 依赖 | 用途 | 备注 |
|------|------|------|
| click, rich | CLI | 与 audit 一致 |
| fastapi, uvicorn | Web | REQ §4.3 已决策 |
| jinja2 | prompt 模板 + HTML 报告 | |
| jsonschema | AI 输出校验 | |
| requests | OSV API / 降级 HTTP | |
| pyyaml | CI 配置解析 | |
| lizard | 多语言圈复杂度/NLOC | 纯 pip，支持 JS/Go/C#/Python |
| 外部 CLI | git, gh, claude | `analyze doctor` 自检 |
| 可选 | madge(node), go | 依赖图增强，缺失降级 |

vendor 资源（一次性下载入库）：`echarts.min.js`（~1MB）、`mermaid.min.js`（~2.8MB）→ 归档 HTML 体积 ~4MB，略超 REQ 预估 1–3MB，属可接受偏差（决策记录 D7）。

## 12. 设计决策记录

| # | 决策 | 理由 |
|---|------|------|
| D1 | 状态存储用 JSON/JSONL 文件，不用 SQLite | 单用户、全局串行、状态量小；文件可读可调试，Web/CLI 读取简单 |
| D2 | daemon 为按需拉起的 detached 进程 + 空闲自动退出，不用 launchd 常驻 | 与「按需启动用完即退」精神一致；免系统级安装 |
| D3 | AI 工具白名单仅 Read/Grep/Glob，不开放 Bash | git 上下文由采集器预先注入，收敛安全边界（REQ §2.4 精神） |
| D4 | 评分缺失维度按剩余权重归一化，不给 0 分 | 避免「数据不可得」被误判为「质量差」，报告显式标注 |
| D5 | 贡献者数据全程不采集（git_context 去除作者字段） | REQ §1.2 明确不分析贡献者，从源头保证 |
| D6 | 架构/依赖图用 mermaid.js 浏览器端渲染 SVG，替代构建期预渲染 | 避免 puppeteer/Chromium 重依赖；最终产物同为矢量 SVG（与 REQ §5.2 措辞偏差已备案） |
| D7 | 归档 HTML 体积 ~4MB（ECharts+mermaid 内联） | REQ「全部自包含」优先于体积预估 |
| D8 | Web 也可发起任务（POST /api/tasks），与 CLI 同一入口逻辑 | 便利性；写操作仍走同一 task 队列，无并发风险（daemon 串行） |
| D9 | 规则评分函数输出 factors[] 因子明细 | 分数可解释，报告展示扣分原因，避免黑盒评分 |
| D10 | 子任务产物先落 state/，归档时组装 | 增量落盘（REQ §4.1）与归档解耦；retry 不重复已完成工作 |
| D11 | 孤儿任务自动重新入队续跑，而非标记 failed 等人工 retry | REQ v6 中断恢复要求：休眠/重启后无需人工干预；幂等重入保证不重复工作 |
| D12 | 不安装 launchd 常驻服务，恢复由 CLI/Web 操作触发 | 保持「按需启动」轻量形态；重启后首次任意命令即恢复。若需全自动可后续补 launchd plist（可选项） |

## 13. 里程碑规划（详见 ANALYSIS-DEV-PLAN.md）

- **M1 基础框架**：目录骨架/依赖、models+store、registry+orchestrator（状态机/超时/重试/取消）、daemon、CLI 全命令（ui 为占位）
- **M2 确定性采集器**：9 个 collector + AuditBridge + OSV
- **M3 AI 引擎与评分**：engine（claude -p）、4 个 prompt 模板 + schema、scoring
- **M4 Web 应用**：FastAPI API + SSE、前端三视图、vendor 资源本地化
- **M5 归档报告**：JSON schema v1 组装、自包含 HTML 模板、latest 链接
- **M6 集成验证**：三个基准仓库端到端（fe-casamiel-admin JS / be-promotion-center Go / be-casamiel-applet-mall C#），对照 REQ 验收
