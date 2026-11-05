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

## 阶段 M5.5：中断恢复与韧性 ✅（2026-11-05，需求补充 v6）

> 需求背景：网络不稳定、宿主机合盖休眠/重启导致执行中断，需自动恢复。

- [x] **T551** daemon 心跳与防双开
  - 完成：2026-11-05。主循环每 10s 原子写 `state/daemon.heartbeat`（pid/ts/current_task）；flock 独占 `state/daemon.lock` 防双 daemon
  - 结果：单测验证锁独占（第二个 daemon 拒绝启动）与心跳读写

- [x] **T552** 孤儿任务自动续跑
  - 完成：2026-11-05。`recover_interrupted_tasks`：running 孤儿 → 中断子任务重置（queued/attempts=0）→ 任务自动重新入队；保留 cancel 意图；写「中断恢复」事件
  - 结果：**真实演练通过**——mock 任务执行中 `kill -9` daemon → `resume` 自动恢复 → 15/15 completed，归档正常；单测覆盖恢复/取消意图保留/无孤儿三态

- [x] **T553** 重试退避与 resume 命令
  - 完成：2026-11-05。失败重试前退避（det 5s / AI 30s，config 可调），退避每秒检查取消；`analyze resume` 命令；`ui` 启动时自动 `recover_and_ensure`
  - 结果：27/27 单测通过（测试中退避置零）

## 阶段 M6：集成验证与收尾

- [x] **T601** 三基准仓库端到端验证
  - 完成：2026-11-05。JS/Go/C# 各完成一次完整真实流水线（CLI 发起 + Web 观察 + 归档报告 + 人工抽查）
  - 结果：
    - **be-promotion-center（Go）**：15/15，总分 62.5/C；业务知识 29 条全带行号级证据（置信度 78-95）+10 缺口 +10 矛盾；P0×2 人工核实属实（Dockerfile CMD 错配、核心领域零单测）
    - **fe-casamiel-admin（JS）**：15/15 全程仅 24.5min，总分 61.9/C；madge 依赖图 68 节点、ESLint 桥接 898 issues、业务定位准确识别（可莎蜜儿后台管理/Vue 2.5.17）
    - **be-casamiel-applet-mall（C#）**：15/15，总分 64.2/C；csproj ProjectReference 图、dotnet 桥接 13484 issues、置信度 0 条目正确联动 gaps；业务定位准确（.NET 6 BFF + Ocelot + 美团/饿了么/达达集成）
    - 跨语言区分度验证：同为 C 级但维度画像迥异（Go 强文档弱测试 / JS 强依赖弱架构 / C# 均衡偏弱文档），评分模型非模板化输出
  - 验证期间修复：cancel 竞态（flag 文件）、retry 终态入队、issues 标题去重、OSV 按包聚合、scoring KLOC 密度 bug（quality 52.4→82.9 修正）、Web 取消按钮可靠性

- [x] **T601a** AI token 消耗优化（2026-11-05 用户确认决策后实施）
  - 决策：L1 激进探索预算（bk≤30/arch≤20 次工具调用）、L2 标准输出瘦身、L3 解读型注入深度裁剪、L6 成本可见化（ai_usage 入归档）；否决 L4 模型分层（统一 qwen3.8-max）、L5 会话复用（保持子任务独立可重试）
  - **实测对比（C# business_knowledge 重跑）**：
    | 指标 | 优化前 | 优化后 | 降幅 |
    |------|--------|--------|------|
    | turns | 56 | 31 | −45% |
    | 成本 | $2.65 | $0.89 | **−66%** |
    | cache_read | 2.59M | 364K | **−86%** |
    | 输出 tokens | 23.9K | 16.7K | −30% |
    | 耗时 | 789s | 464s | −41% |
  - 质量护栏（可接受微损）：知识条目 30→21（设计区间内）、置信度中位 83.5→82（持平）、平均证据 2.2→1.9、gaps 10→10、矛盾 9→8、readiness 波动正常
  - 预估单仓库全程 AI 成本：$2.9-4.5 → **$2.0-2.2（−52%）**，AI 总时长 ~30min → ~17min

- [x] **T602** 文档与收尾
  - 完成：2026-11-05。analysis/README（含 resume 与 Web 进程重启指引）、AGENTS.md 增补 audit/analyze 命令与架构注记、REQ 全部待决策项标记落定（schema v1 + prompt 体系）、DEV-PLAN 全程回填
  - 验收：新会话按 analysis/README.md 可独立跑通（setup.sh → doctor → start → ui → report）

## 阶段 M7：多语言支持补足（2026-11-05 用户确认四项决策后启动；同日追加四项决策）✅ 已完成（P0+P1；P2 的 T705 搁置）

> 背景：repos/augmn 125 仓库中，除 Go(24)/C#(17)/TS(15)/Vue(13)/JS(4) 外还有 Python(22)/Shell(9)/Dart(6)/Java(1)/Ruby(1)/HTML(1)/文档空仓库(9)/fork(2)。
> 已确认决策：① 引入 ruff（Python）+ shellcheck（Shell）本地 lint；② P0+P1+P2 全部补足；③ 无代码仓库（生产代码 <100 行）跳过 AI 出简版报告；④ fork 仓库 start 预检拒绝，完全不分析。
> **追加决策（2026-11-05 T706 期间）**：⑤ archived 仓库同 fork 一律 start 拒绝（29/125 为归档仓库，REQ 与计划均未覆盖，DESIGN D15）；⑥ 验证分两阶段——采集层用新增 `--no-ai` 零成本跑，真实 AI 只对 Python/Shell/Dart 三仓库全量（DESIGN D16）；⑦ **开发成本纪律 + `--ai-stub` 桩执行 + 单任务 AI 预算护栏 $5**（需求方明确要求：token 消耗在开发测试过程同样要控住，DESIGN D17/D18）；⑧ **T705（Java/Ruby 支持包）搁置**——org 内唯二的 Java/Ruby 仓库都是 archived，按 ⑤ 一律不分析，本任务无验收载体（已交付的采集器代码与零成本 fixture 回归保留，不回退）。
> 成本红线：全部补足位于确定性采集层，**AI token 零增量**；空仓库守护使 9 个文档仓库 AI 成本归零。M7 验证实际 AI 花费 **$6.98**（含一次误跑 $1.52），≤ $12 上限。

- [x] **T701** P0：空仓库守护 + fork 预检 + Python 增强
  - 内容：orchestrator 守护（production lines <100 → ai.*/scoring 全部 skipped，archive 照常出简版报告）；service fork 预检（gh api .fork 字段，API 不可达放行并标注）；docs 采集器 Python docstring 改用 ast 精确统计；overview 优先读 repos/<org>-summary.json 语言分布（省 API 调用）；报告主语言 fallback 到本地统计
  - 验收（2026-11-05 实测）：ai-env-setup（0 生产行）走守护路径 → 10/15 completed、5 skipped、`repository_class=documentation_or_empty`、`ai_usage.total_cost_usd=0.0`、简版 HTML 带📄横幅；sqlfluff `start` 被拒（gh api .fork=true 现场核对）；**归档仓库（追加决策⑤）同样被拒**：fe-casamiel-admin-app、ops-infrastructure；预检合并为单次 `gh api`（同取 .fork/.archived），404（非 GitHub 托管）与不可达均放行并落标注事件；单测 `test_multilang.py` 守护/拒绝/放行 6 项

- [ ] **T702** P0：ruff lint 集成（Python 22 仓库）
  - 内容：`python -m ruff check --output-format json --select E,F,W,S,B`；quality 采集器聚合（severity 映射：E9/F82x→high、F/B→medium、E/W→low）；S 系列（bandit 安全规则）同时供 security 采集器引用
  - 验收（2026-11-05 实测，`--no-ai` 零成本）：**ops-mdm** `local_lint.ruff` = 207 条（high 3 / medium 65 / low 139，TOP：E501 113、F401 47、W291 11、S113 8），S 系列经 quality 产物传递给 security → `python_bandit_rules` 11 条（S113 8 / S311 2 / S105 1）；**da-etl**（197 个 .py / 21062 生产行）= **3282 条**（high 5 / medium 261 / low 3016，TOP：E501/W293/W291/W292/S608），`python_bandit_rules` **143 条**（S608 SQL 字符串拼接 96、S113 25、S506 8…）→ 评分 49.9 D；ruff 缺失/非 Python 仓库 → `found:false` + 建议文案（单测覆盖，含 `test_run_ruff_no_python`）

- [ ] **T703** P1：Dart 支持包（6 仓库）
  - 内容：pubspec.yaml 依赖解析 → OSV Pub 生态；`import 'package:x'` 包级依赖图；`_test.dart`/test/ 测试识别 + flutter_test/test 框架；`//` 注释 + 大写开头公共 API 统计；危险模式（Process.run/dart:mirrors）；复杂度/lint found:false 兜底（不引入 Flutter SDK）
  - 验收（2026-11-05 实测）：fe-dropdown-textfield-ui → `manifests_detected=["pubspec.yaml"]`、外部依赖 5 项、`dependency_graph.tool="pubspec + package import"`（含自引用排除）、`frameworks={"flutter_test":true}` + 2 个 `_test.dart`、Dart 注释 74/1717 行（4.31%）、`public_api_docs.Dart` 14 个公共 API（documented 0）、危险模式（dart_process_run/dart_mirrors）0 命中且入 patterns_matched 清单、OSV Pub 因 pubspec 为范围版本（^x.y.z）走规范兜底文案、复杂度走 lizard（files=3）、lint `found:false`（不引入 Flutter SDK）

- [ ] **T704** P1：Shell 支持包（9 仓库）+ shellcheck
  - 内容：shellcheck lint（分批调用、severity 映射 error→high/warning→medium/info→low/style→info）；危险模式（eval、curl|bash、rm -rf 未引号变量、chmod 777）；source/. 脚本调用图；bats/*_test.sh 测试识别
  - 验收（2026-11-05 实测）：ops-k8s-deploy（112 个 .sh / 1528 行）→ `local_lint.shellcheck` 659 条（high 110 / medium 172 / low 369 / info 8；TOP：SC2086 369、SC2148 109 缺 shebang、SC2164 105 缺 cd 失败检查、SC2154 64 未引用变量）、`dependency_graph.tool="shell source graph"`（脚本级 source/. 调用）、危险模式 `shell_rm_unquoted_var` 23 处 high、Shell 注释 244/1121（21.77%）、bats 未使用 → 测试框架兜底建议已按主语言给出「Shell: bats（配合 shellcheck）」；lizard 不支持 Shell → complexity files=0 兜底

- [ ] **T705** P2：Java + Ruby 支持包 —— **已搁置**（2026-11-05 需求方决定；不计入 M7 完成项）
  - 内容（原计划）：Java——pom.xml/build.gradle 解析 → OSV Maven、junit/mockito 识别、jacoco 产物、公共 API/javadoc 统计；Ruby——Gemfile.lock 精确版本 → OSV RubyGems、rspec/minitest、eval/system/Marshal 模式
  - 搁置理由：org 内 Java 与 Ruby 各只有 1 个仓库（fe-casamiel-admin-app、ops-infrastructure），**两者均已 archived**；按需求方既定原则「fork 或 archived 的仓库一律不分析」，本任务没有可分析载体，端到端验收无法成立（两仓库 `analyze start` 均返回 archived 策略拒绝，已现场核对）。
  - 已交付部分不回退：采集器代码（`_parse_pom` / `_parse_gemfile` / OSV Maven·RubyGems 生态 / junit·mockito·rspec·jacoco 识别 / `java_runtime_exec`·`java_deserialization`·`ruby_eval`·`ruby_marshal_load` 危险模式）在 a28f586 已落地，保留**零成本** fixture 回归 `test_multilang.py::test_javaruby_collectors_end_to_end`（语言统计 / manifest 解析 / OSV 入查 / 框架识别 / javadoc·rdoc 注释 / 公共 API / 危险模式 / lizard 复杂度）。若将来出现非归档 Java/Ruby 仓库，支持包可直接使用，只需补一次 `--no-ai` 采集层验证（$0）。

- [x] **T706** M7 集成验证与收尾（完成 2026-11-05）
  - 内容：两阶段验证（追加决策⑥）+ 拒绝路径验证 + doctor 增补 ruff/shellcheck + DESIGN D13-D18 + README/AGENTS 更新 + 开发成本纪律落地（决策⑦：`--ai-stub`、预算护栏）
  - **阶段一（$0，`--no-ai` / 空仓库守护）**：

    | 任务 | 仓库 | 路径 | 结果 | AI 成本 |
    |------|------|------|------|---------|
    | 224457 | Shell ops-k8s-deploy | --no-ai | 11/15（4 AI skipped），55.2 D（missing 3） | $0.00 |
    | 224458 | Dart fe-dropdown-textfield-ui | --no-ai | 11/15，70.2 C（missing 2） | $0.00 |
    | 230735/233423 | Python ops-mdm | --no-ai | 11/15，56.5 D（missing 2；OSV 修复后重跑） | $0.00 |
    | 224459 | 空仓库 ai-env-setup | 守护路径 | 10/15（4 AI + scoring skipped），简版报告 | $0.00 |
    | 233300 | Shell ops-k8s-deploy | --ai-stub | **15/15**（4 AI 桩 0.0s），55.8 D，报告不落 reports/ | $0.00 |
    | 234748 | Python da-etl | --no-ai | 11/15，49.9 D（ruff 3282 / bandit 143 / 197 个 .py） | $0.00 |

  - **阶段二（真实 AI，3 仓库全量）**：ops-mdm $2.055 → 54.1 D（0 missing）、ops-k8s-deploy $1.543 → 51.7 D、fe-dropdown-textfield-ui $1.865 → 63.5 C；全部 15/15 completed
  - **拒绝验证**：sqlfluff（fork）、fe-casamiel-admin-app + ops-infrastructure（archived）→ `start` 报错退出，`state/tasks/` 无残留任务目录
  - **验证期间发现并修复**：
    1. **OSV 对 PyPI 从未生效**（严重）：requirements.txt 解析出 `==5.2.0` 约束串，而查询要求 `^\d+\.\d+` → 22 个 Python 仓库的依赖漏洞全部静默 `found:false`，兜底文案还误导为"范围版本"。修复后 ops-mdm 实测 **45 依赖入查 / 11 包受影响 / 129 条漏洞**，安全维度从"无数据"变为有实测依据（同仓库评分 60.6 C → 54.1 D）；单测 2 项（PyPI 归一化 + Pub/Maven/RubyGems 生态映射）
    2. **`--no-ai` 与 `retry` 交互导致真实 AI 误跑**：skip 分支条件写成「状态非 skipped 才跳过」，未列入级联的 AI 子任务在 retry 后反而放行执行，白烧 **$1.52**。改为「no_ai 时 AI 子任务任何状态都不得执行」，并加回归测试 `test_no_ai_survives_retry`（已验证：旧代码下该测试红）
    3. 测试框架兜底建议只列 JS/Go/C#，M7 新语言未覆盖 → 改为按生产代码扩展名分布给出（实测 ops-k8s-deploy 输出「Shell: bats（配合 shellcheck）」）；CI 测试步骤正则补 bats/rspec/flutter test/mvn·gradle test
    4. **daemon 不热更新**（操作坑）：改完 collectors/core 必须重启 daemon，否则旧代码继续执行 → 已写入 README 与 AGENTS.md
    5. 兜底文案两处只列 M7 前的生态：测试框架建议（已由 `test_osv_multilang.py` 断言按主语言输出）与依赖清单未检出提示（补全 pubspec/pom/build.gradle/Gemfile/pyproject，da-etl 实测输出新文案）
  - **开发成本纪律（需求方 2026-11-05 要求）**：`--ai-stub` schema-valid 桩（`ai/stub_outputs/*.json`，桩产物同样过 jsonschema；prompt 仍完整渲染并记录 `prompt_chars`；`_ai_meta.stub=true`、cost=0；报告只落 `state/tasks/<id>/report/`，不写 reports/ 且不动 latest 指针，HTML 顶部🧪横幅）+ 单任务 AI 预算护栏 `MAX_TASK_AI_COST_USD=$5`（触顶后剩余 AI「计划跳过」，不阻塞 scoring；`status`/`history` 显示累计成本与上限）→ DESIGN D17/D18，README 新增「开发成本纪律」三档选择表
  - **收尾核对**：`analyze doctor` **17/17**（含 lint:ruff 0.17.3、lint:shellcheck）；单测 **54 → 74 全绿**（test_multilang 23 / test_osv_multilang 4 / test_dev_modes 6 + 既有 41）；M7 验证 AI 合计 **$6.98 ≤ $12**（其中事故 $1.52；6 次 `--no-ai` + 1 次 `--ai-stub` 均为 $0）

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
| R7 | archived 仓库（29/125）无处理策略，且占掉 M7 的 Java/Ruby 两个验证目标 | T705/T706 | 已决策⑤：与 fork 同等 `start` 拒绝；由此触发决策⑧——T705 搁置（采集器代码 + 零成本 fixture 回归保留，见 T705 条目） |
| R8 | 开发/测试过程为验证全流程而调用真实 AI，成本不可控（实测一次误跑 $1.52） | T706 | 已决策⑦：`--no-ai`（采集层）/`--ai-stub`（全流程桩）/`--mock`（联调）三档零成本 + 单任务 $5 预算护栏 + 回归测试；纪律写入 README/AGENTS |
| R9 | daemon 不热更新：改代码后旧 daemon 仍执行旧采集逻辑，结论静默失真 | T706 | 已文档化（README 重启指引 + AGENTS 警示）；如需自动化可在 M8 评估「daemon 按代码指纹自动退出重启」 |
