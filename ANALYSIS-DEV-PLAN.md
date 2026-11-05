# 仓库全面分析工具 — 开发任务清单

> 基于 `REPO-ANALYSIS-REQ.md` v6 与 `ANALYSIS-DESIGN.md` v1。
> 执行方式：AI 驱动开发——按任务编号顺序执行，每完成一个任务更新 checkbox 与结果记录；人类通过本文档了解进度和质量。

## 测试基准仓库

沿用 audit 的三个基准仓库（覆盖三种目标语言）：

| 仓库 | 语言 | 验证重点 |
|------|------|----------|
| `augmn/fe-casamiel-admin` | Vue/JavaScript | JS 采集器、madge 依赖图、audit ESLint 桥接 |
| `augmn/be-promotion-center` | Go | go mod 解析、go mod graph、audit golangci 桥接 |
| `augmn/be-casamiel-applet-mall` | C# | csproj 解析、ProjectReference 图、audit dotnet 桥接 |

**验收要求**：M6 阶段三个仓库各完成一次端到端分析，产出归档报告并人工抽查质量。

---

## 阶段 M1：基础框架 ✅（2026-11-05）

- [x] **T101** 项目骨架与环境
  - 完成：2026-11-05。`analysis/` 骨架（audit 同构布局）、pyproject/requirements/setup.sh（uv + Python 3.11）、`bin/analyze`（Click）、.gitignore 增补
  - 结果：`analyze doctor` 15/15 通过（git/gh/claude/9 个 Python 依赖/vendor×2/gh 认证）

- [x] **T102** 数据模型与状态存储
  - 完成：2026-11-05。`core/models.py`（Task/SubtaskState/状态枚举）、`core/store.py`（task.json 原子写 tmp+replace、events.jsonl seq 单调、前缀查找、daemon pid）
  - 结果：单元测试通过（roundtrip/seq/原子写/progress）

- [x] **T103** 子任务注册表与编排器
  - 完成：2026-11-05。`registry.py`（15 子任务 DAG 声明 + handler 注册 + Kahn 拓扑排序）、`orchestrator.py`（状态机、SIGALRM 超时、重试、失败传播 skipped、always_run、cancel 边界检查、幂等重入、--ref worktree）
  - 结果：mock 全流程/失败传播/retry 重入/取消/超时 6 个单测通过

- [x] **T104** 执行器 daemon
  - 完成：2026-11-05。detached 拉起、pid 检测、FIFO 串行、空闲 TTL 退出、孤儿恢复、daemon.log
  - 结果：冒烟验证 daemon 自动拉起并连续消费 3 个任务

- [x] **T105** CLI 命令集
  - 完成：2026-11-05。start(--ref/--mock)/status(rich 表)/history/cancel/retry/report/doctor/ui/_daemon；`core/service.py` 共享服务层（CLI 与 Web 复用，决策 D8）
  - 结果：全命令冒烟走通 mock 任务生命周期

## 阶段 M2：确定性采集器 ✅（2026-11-05，代码完成）

- [x] **T201** Collector 基类与公共工具 — 排除规则/语言映射/测试路径判定/not_found 契约/_meta 注入
- [x] **T202** overview + git_context — gh api 全字段 + 降级；commit 摘要**无作者信息**（决策 D5）
- [x] **T203** structure + docs + tests — 行数三分类、目录树；README 章节/注释率/API 文档注释；测试清点/CI 只读/覆盖率产物探测
- [x] **T204** dependencies — 4 生态 manifest + 依赖图（madge/go mod graph/csproj ProjectReference/python import）+ 降级标注
- [x] **T205** AuditBridge + quality + security — audit latest/report.json 按 dimension 分流 + 过期标注；lizard 复杂度；OSV querybatch；14 条危险模式规则库
- [x] **T206** performance — 4 类静态反模式（循环 IO/循环拼接/async 同步阻塞/无 LIMIT SELECT）+ 边界声明
  - ⚠️ 验收说明：M2 采集器已过单元测试与 mock 流水线，**真实仓库数据质量验收在 T601 执行**

## 阶段 M3：AI 引擎与评分 ✅（2026-11-05，代码完成）

- [x] **T301** AI engine — `claude -p --output-format json --allowedTools Read,Grep,Glob`（只读白名单，决策 D3）、cwd=目标仓库、超时、JSON 提取（代码块/裸 JSON）、失败衔接重试
- [x] **T302** 提示词模板与 schema — 4 套 `*.md.j2`（architecture/business_knowledge/conclusions/summary）+ 4 套 jsonschema；business_knowledge 内嵌 REQ 置信度分级标准；注入数据裁剪（_trim）；_ai_meta 非确定性标注
  - ⚠️ 真实 AI 产物 schema 通过率验收在 T601 执行（R1/R3 风险项）
- [x] **T303** scoring — 7 规则评分（factors 因子明细）+ 2 AI 评分 + 缺失维度权重归一化（决策 D4）+ A–F 等级；单测覆盖全缺失/良好仓库/critical 漏洞/归一化

## 阶段 M4：Web 应用 ✅（2026-11-05，代码完成）

- [x] **T401** FastAPI 后端 — /api/health、tasks CRUD、events 增量、**SSE stream**、preview 增量组装、cancel/retry、/reports 静态服务；仅绑定 127.0.0.1
  - 结果：curl 冒烟全端点通过；修复前缀 task_id 路径 bug
- [x] **T402** 前端三视图 — 原生 JS：任务列表+发起表单；工作流四阶段流水线（状态色/耗时/重试标记/点击查看产物）；SSE 实时事件流 + 增量预览
  - ⚠️ 浏览器人工体验验收在 T601 执行
- [x] **T403** vendor 资源本地化 — echarts@5.5.0（1.0MB）+ mermaid@10.9.1（3.3MB）版本锁定入库

## 阶段 M5：归档报告 ✅（2026-11-05）

- [x] **T501** 归档 JSON — schema v1：metadata（limitations/data_sources/audit_refs/prompt_versions）+ scores + 11 chapters + issues 聚合（去重/P0-P2 排序）+ knowledge + subtasks_status
  - 结果：mock 任务产出 16.6KB JSON，结构自校验通过
- [x] **T502** 自包含 HTML — Jinja2 模板 + ECharts/mermaid 内联（4.4MB 单文件）+ 侧边目录 + 评分图表 + 问题筛选 + 置信度 badge + 头部标注区；模板全路径 Undefined 防御
  - 结果：mock 数据离线渲染成功；修复 pinned_ratio Undefined 崩溃
- [x] **T503** 归档路径与 latest — `reports/<org>/<repo>/analysis/<ts>.{html,json}` + latest 符号链接；修复 task.report 被 orchestrator 覆盖 bug（handler 改 ctx.task 统一落盘）
  - 结果：与 audit 时间戳目录并存互不干扰

## 阶段 M5.5：中断恢复与韧性（新增，2026-11-05 需求补充）

> 需求背景：网络不稳定、宿主机合盖休眠/重启导致执行中断，需自动恢复。

- [ ] **T551** daemon 心跳与防双开
  - 依赖：T104
  - 内容：daemon 主循环每 10s 写 `state/daemon.heartbeat`（pid/ts/当前任务）；flock 独占锁防双 daemon
  - 验收：双 daemon 并发拉起时后者自动退出；心跳文件随循环更新

- [ ] **T552** 孤儿任务自动续跑
  - 依赖：T551
  - 内容：daemon 启动时扫描 running 孤儿任务 → 中断子任务重置（queued/attempts=0）→ 任务自动重新入队（**不再标记 failed 等人工 retry**）；保留用户 cancel 意图；写「中断恢复」事件
  - 验收：模拟孤儿任务（手改 running + kill daemon）→ 重启后自动续跑且 completed 子任务不重复执行

- [ ] **T553** 重试退避与 resume 命令
  - 依赖：T103
  - 内容：子任务失败重试前退避等待（det 5s / AI 30s，可配置），退避期间响应取消；`analyze resume` 命令（扫描恢复 + 拉起 daemon）；`ui` 命令自动触发恢复检查
  - 验收：单测覆盖退避与恢复；resume 对正常/孤儿/无任务三态输出正确

## 阶段 M6：集成验证与收尾

- [ ] **T601** 三基准仓库端到端验证
  - 依赖：全部
  - 内容：JS/Go/C# 各跑完整真实流水线（CLI 发起 + Web 全程观察 + 归档报告），对照 REQ 逐章验收；含 M2/M3/M4 遗留的真实数据验收项
  - 验收：三份归档报告章节完整、评分可解释、业务知识清单含置信度与证据；问题修复记录

- [ ] **T602** 文档与收尾
  - 依赖：T601
  - 内容：README 更新、AGENTS.md 增补 analyze 命令、REQ 待决策项 #1/#2 标记落定、DEV-PLAN 结果回填
  - 验收：新会话按 README 可独立跑通一次分析

---

## 风险与确认点（执行中遇到即与需求方确认）

| # | 风险/确认点 | 触发时机 | 状态 |
|---|------------|----------|------|
| R1 | claude headless 的 --allowedTools 行为与预期不符（如仍询问权限） | T301/T601 | 待真实 AI 验证 |
| R2 | OSV API 对 C# NuGet 版本范围查询命中率低 | T205/T601 | 待验证 |
| R3 | AI 产物质量不稳定（证据缺失/置信度虚高） | T302/T601 | 待验证 |
| R4 | 归档 HTML 体积超 4MB 或 mermaid 浏览器渲染兼容问题 | T502 | 体积 4.4MB（mock 数据），可接受 |
| R5 | madge/go 工具链缺失导致依赖图降级频繁 | T204/T601 | 待验证 |
| R6 | 宿主机休眠期间 SIGALRM 时钟语义不可靠（唤醒后可能立即超时） | T551-T553 | 重试 + 自动续跑兜底，文档注明局限 |
