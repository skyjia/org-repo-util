# 仓库全面分析工具 — 开发任务清单

> 基于 `REPO-ANALYSIS-REQ.md` v5 与 `ANALYSIS-DESIGN.md` v1。
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

## 阶段 M1：基础框架

- [ ] **T101** 项目骨架与环境
  - 依赖：无
  - 内容：`analysis/` 目录结构、`pyproject.toml`（uv）、`requirements.txt`、`setup.sh`、`bin/analyze` 入口、`.gitignore` 增补（`analysis/state/`、`analysis/.venv/`）
  - 验收：`uv run analyze --help` 正常输出；`analyze doctor` 检出 git/gh/claude 可用性与版本

- [ ] **T102** 数据模型与状态存储
  - 依赖：T101
  - 内容：`models.py`（Task/Subtask dataclass、状态枚举）、`store.py`（task.json 原子读写、events.jsonl 追加 + seq、任务目录布局、daemon.pid）
  - 验收：单元测试覆盖：状态流转合法性、原子写、事件 seq 单调

- [ ] **T103** 子任务注册表与编排器
  - 依赖：T102
  - 内容：`registry.py`（15 个子任务声明：名称/类型/依赖/超时/handler 占位）、`orchestrator.py`（拓扑排序、状态机、超时 kill、自动重试一次、失败跳过 + 下游 skipped、cancel 边界检查、幂等重入）
  - 验收：用 mock handler 单元测试：正常流、单点失败传播、取消、retry 重入跳过已完成

- [ ] **T104** 执行器 daemon
  - 依赖：T103
  - 内容：`daemon.py`（detached 拉起、pid 存活检测、FIFO 队列轮询、空闲 TTL 自动退出、崩溃恢复标记 interrupted、daemon.log）
  - 验收：`analyze start` 后 daemon 自动拉起并消费 mock 任务；daemon 被 kill 后再次 start 自动重启；running 孤儿任务被标记 failed(interrupted)

- [ ] **T105** CLI 命令集
  - 依赖：T104
  - 内容：`cli.py`——start（含 --ref 解析 commit SHA）/ status（rich 进度表）/ history / cancel / retry / report / doctor / ui（占位）/ _daemon
  - 验收：全命令走通 mock 任务生命周期：start→status 可见进度→（cancel|等待完成）→history/report 输出正确

## 阶段 M2：确定性采集器

- [ ] **T201** Collector 基类与公共工具
  - 依赖：T103
  - 内容：`collectors/base.py`（输出契约 `_meta`、缺失数据 `found:false+suggestion` 结构、文件遍历排除规则、语言扩展名映射表）
  - 验收：排除规则在基准仓库验证（node_modules 不计入行数）

- [ ] **T202** overview + git_context 采集器
  - 依赖：T201
  - 内容：gh api 元数据（REQ §3.1 全字段）+ 降级路径；git_context（commit 消息摘要，**无作者信息**，首末 commit、tag/分支）
  - 验收：三基准仓库产出完整；gh 不可用时降级标注正确

- [ ] **T203** structure + docs + tests 采集器
  - 依赖：T201
  - 内容：行数统计（生产/测试/生成分类）、目录树；README 章节检查、注释率、API 文档注释比例；测试清点、框架识别、空测试启发式、CI 配置读取、覆盖率产物探测
  - 验收：三基准仓库数据人工抽查合理（行数与 tokei 量级一致）

- [ ] **T204** dependencies 采集器 + 依赖图
  - 依赖：T201
  - 内容：四种 manifest 解析；依赖图：madge（JS，缺失降级）/ go mod graph / csproj ProjectReference / Python import；nodes/edges 输出
  - 验收：三基准仓库各产出模块级依赖图数据；无工具时按 REQ §3.3 标注省略原因

- [ ] **T205** AuditBridge + quality + security 采集器
  - 依赖：T201
  - 内容：读 audit latest/report.json 按 dimension 分流（含过期标注，REQ §1.3）；lizard 复杂度集成；OSV batch API 查询；危险模式启发式规则库
  - 验收：fe-casamiel-admin 桥接到 ESLint 结果并标注 audit 时间；OSV 对 go.mod 精确版本返回可解析；audit 产物缺失时 found:false 兜底

- [ ] **T206** performance 采集器
  - 依赖：T201
  - 内容：静态反模式规则库（循环内 IO/DB、async 上下文 sync 调用等），命中含证据片段；边界声明字段
  - 验收：三基准仓库运行无误报爆炸（命中数人工抽查）

## 阶段 M3：AI 引擎与评分

- [ ] **T301** AI engine（claude headless 封装）
  - 依赖：T103
  - 内容：`ai/engine.py`——subprocess 调用（-p、--output-format json、--allowedTools Read,Grep,Glob、cwd=目标仓库）、超时 kill、JSON 代码块提取、jsonschema 校验、失败重试衔接
  - 验收：对基准仓库跑通一个最小 prompt，返回合法 JSON；超时与非法输出路径有测试

- [ ] **T302** 提示词模板与输出 schema（4 套）
  - 依赖：T301
  - 内容：architecture / business_knowledge / conclusions / summary 的 `*.md.j2` + `schemas/*.json`；business_knowledge 模板内嵌 REQ 第 6 章置信度分级标准；数据注入裁剪逻辑
  - 验收：三基准仓库各 AI 子任务产物通过 schema 校验；knowledge 条目均含 evidence 与 confidence

- [ ] **T303** scoring 评分模型
  - 依赖：T202-T206, T302
  - 内容：7 个规则评分函数（factors 因子明细）+ 2 个 AI 评分接入 + 缺失维度权重归一化 + 加权总分 + A–F 等级
  - 验收：三基准仓库评分可解释（factors 完整）；缺失维度场景归一化正确

## 阶段 M4：Web 应用

- [ ] **T401** FastAPI 后端
  - 依赖：T104
  - 内容：`web/app.py + api.py`——tasks 列表/详情、SSE 事件流（tail events.jsonl）、preview 增量组装、report 元信息、POST 发起/cancel/retry、归档静态 serve；仅绑定 127.0.0.1
  - 验收：curl 全端点走通；SSE 在任务执行中实时推送事件

- [ ] **T402** 前端三视图
  - 依赖：T401
  - 内容：原生 JS/CSS——任务列表卡片+发起表单；工作流 DAG 流水线图（SVG 状态色/耗时/重试标记/节点点击看产物）；执行节奏事件流 + 增量报告预览（占位/刷新更新）
  - 验收：浏览器中完整观察一次基准仓库分析全过程；Web 退出后任务继续、重开可恢复视图

- [ ] **T403** vendor 资源本地化
  - 依赖：T401
  - 内容：下载 echarts.min.js / mermaid.min.js 入 `web/static/vendor/`（版本锁定并记录）
  - 验收：断网环境 Web 界面正常

## 阶段 M5：归档报告

- [ ] **T501** 归档 JSON 组装
  - 依赖：T303
  - 内容：`reporters/json_report.py`——schema v1 全字段组装（设计文档 §10）、limitations/data_sources 声明、subtasks_status
  - 验收：三基准仓库 JSON 通过 schema v1 自校验；含 AI 非确定性标注

- [ ] **T502** 自包含 HTML 报告
  - 依赖：T501, T403
  - 内容：`report.html.j2` + `html_report.py`——数据/JS 全内联单文件；侧边目录、章节折叠、ECharts SVG 图表、mermaid 架构/依赖图、问题筛选、置信度 badge、头部标注区（REQ §5.2 全项）
  - 验收：离线双击打开渲染完整；文件体积记录；11 章节齐全（含失败/缺失占位）

- [ ] **T503** 归档路径与 latest 链接
  - 依赖：T502
  - 内容：`report.archive` 子任务落盘 `reports/<org>/<repo>/analysis/<ts>.{html,json}` + latest 符号链接
  - 验收：与 audit 报告目录互不干扰；latest 指向正确

## 阶段 M6：集成验证与收尾

- [ ] **T601** 三基准仓库端到端验证
  - 依赖：全部
  - 内容：JS/Go/C# 各跑完整流水线（CLI 发起 + Web 全程观察 + 归档报告），对照 REQ 逐章验收
  - 验收：三份归档报告章节完整、评分可解释、业务知识清单含置信度与证据；问题修复记录

- [ ] **T602** 文档与收尾
  - 依赖：T601
  - 内容：`analysis/README.md`（使用指南）、AGENTS.md 增补 analyze 命令说明、REQ 待决策项 #1/#2 状态更新为已落定、DEV-PLAN 结果回填
  - 验收：新会话按 README 可独立跑通一次分析

---

## 风险与确认点（执行中遇到即与需求方确认）

| # | 风险/确认点 | 触发时机 |
|---|------------|----------|
| R1 | claude headless 的 --allowedTools 行为与预期不符（如仍询问权限） | T301 |
| R2 | OSV API 对 C# NuGet 版本范围查询命中率低 | T205 |
| R3 | AI 产物质量不稳定（证据缺失/置信度虚高） | T302/T601 |
| R4 | 归档 HTML 体积超 4MB 或 mermaid 浏览器渲染兼容问题 | T502 |
| R5 | madge/go 工具链在目标环境缺失导致依赖图降级频繁 | T204 |
