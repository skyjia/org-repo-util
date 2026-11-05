# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**org-repo-util** is a Fish shell-based CLI tool for managing GitHub organization repositories. It supports batch cloning repos, syncing updates, and exporting metadata as JSON. Pure Fish shell + `jq`, no Python.

## Commands

```fish
# Interactive menu
fish src/main.fish

# Batch clone (includes public + private repos)
fish src/main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]

# Sync updates (supports parallel execution)
fish src/main.fish sync [--dry-run] [-j N|--jobs N]

# Export repo metadata as JSON
fish src/main.fish export [--org <org>] [--output <file>] [--local] [--languages]

# Scan for deleted, renamed, or corrupted repos
fish src/main.fish scan

# Help
fish src/main.fish --help

# 代码审计（Python 工具，见 audit/ 与 AUDIT-DESIGN.md）
audit/bin/audit repo <path> [--save]

# 仓库全面分析（Python 工具，见 analysis/ 与 ANALYSIS-DESIGN.md；需求 REPO-ANALYSIS-REQ.md）
analysis/bin/analyze start <org>/<repo> [--ref <branch|tag|commit>] [--no-ai] [--ai-stub]
analysis/bin/analyze ui                # Web 可视化：工作流/执行节奏/增量报告（按需启动）
analysis/bin/analyze status | history | cancel | retry | resume | report | doctor
```

## Project Structure

- `src/main.fish` — CLI entry point (arg parsing + interactive menu)
- `src/common.fish` — Shared utilities (logging, repo scanning, prereq checks)
- `src/commands/clone.fish` — Batch clone with pattern filtering and parallel execution
- `src/commands/sync.fish` — Sync all cloned repos (pull --rebase) with dry-run and parallel execution support
- `src/commands/export.fish` — Export repo metadata as JSON via `gh api` + `jq`
- `src/commands/scan.fish` — Scan for deleted, renamed, or corrupted repos
- `repos/<org>/<repo>/` — Cloned repositories organized by organization
- `logs/errors.log` — Append-only error log (session headers + error details with raw stderr)
- `audit/` — 代码审计工具（Python：ESLint/golangci-lint/dotnet-format 静态扫描 + AI 辅助，见 AUDIT-DESIGN.md）
- `analysis/` — 仓库全面分析工具（Python：异步子任务流水线 + claude headless AI 解读 + FastAPI Web 控制台，见 ANALYSIS-DESIGN.md）
- `reports/<org>/<repo>/` — audit 报告归档（`<timestamp>/` + latest）；分析报告归档于 `analysis/` 子目录（与 audit 隔离）

## Requirements

- Fish shell
- GitHub CLI (`gh`), authenticated via `gh auth login`
- `jq` for JSON processing (`brew install jq`)

## 多版本工具管理

本机使用 [asdf](https://asdf-vm.com/) 管理多版本工具环境，已安装的工具包括：
- **Java** (多个 JDK 版本)
- **Ruby** (多个 Ruby 版本)
- **Node.js** (多个 Node.js 版本)

遇到版本相关问题时（如工具版本不兼容、需要切换版本等），可以利用 asdf 辅助解决：
- `asdf list` — 查看已安装的工具和版本
- `asdf global <tool> <version>` — 设置全局默认版本
- `asdf local <tool> <version>` — 设置当前目录版本
- `asdf install <tool> <version>` — 安装指定版本

## Architecture Notes

- Pure Fish shell — no Python dependencies
- `gh api` for all GitHub API calls, `jq` for JSON parsing/filtering
- Clone fetches both public and private repos via `gh api "orgs/{org}/repos" -q type=all`
- Clone and sync both support parallel execution via Fish job control
- Sync uses configurable `-j/--jobs` flag (default: 1); spawns background Fish processes
- Export supports optional language breakdown via `--languages` flag (calls `/repos/{org}/{repo}/languages` per repo)
- Export outputs `primary_language` field (renamed from `language` for clarity)
- Scan uses secondary verification with `git ls-remote` when `gh api` fails to avoid false positives
- Error details are written to `logs/errors.log` (append-only), terminal shows summary only
- Batch operations continue on failure; failed clones captured via per-repo temp stderr files
- analysis 混合执行：9 个确定性采集器（复用 audit 产物/lizard/OSV）+ 4 个 AI 子任务（`claude -p` 只读白名单 Read/Grep/Glob，解读型任务空白名单）+ 规则/AI 混合评分（9 维加权 → A–F）
- analysis 全局串行流水线：子任务状态机 + 增量落盘（JSON/JSONL 文件存储）；中断自动恢复（daemon 心跳 + 孤儿任务自动重新入队 + `analyze resume`）；AI 产物标注 `_ai_meta` 非确定性
- analysis 归档 HTML 为自包含单文件（内联 ECharts/mermaid，离线可分享）；Web 控制台按需启动（localhost，用完即退，与执行器解耦）
- analysis 多语言（M7）：Python 走 ruff（E/F/W/S/B，S 系列 bandit 结果供 security 维度复用）、Shell 走 shellcheck；Dart/Java/Ruby 用 manifest 解析（pubspec/pom.xml+build.gradle/Gemfile.lock → OSV Pub/Maven/RubyGems）+ 语言特有启发式；复杂度通用走 lizard（Shell 不支持 → found:false 兜底）
- analysis 三类闸门（均为用户决策，见 DESIGN D13–D16）：fork 与 archived 仓库在 `start` 预检阶段拒绝（一次 `gh api` 同取 `.fork`/`.archived`，API 不可达或 404 时放行并落标注事件）；生产代码 <100 行触发空仓库守护（跳过全部 AI 与评分，归档出简版报告，零 AI 成本）；`--no-ai` 跳过全部 AI 子任务但保留采集/评分/归档，属「计划跳过」不阻塞下游
- ⚠️ daemon 不热更新：改动 `analysis/collectors/` 或 `core/` 后必须 `kill $(cat analysis/state/daemon.pid)` 并清理 `state/daemon.lock`/`daemon.pid` 残留，否则仍用旧代码执行（采集结论会静默失真）
- ⚠️ 开发成本纪律（需求方要求，与工具运行时成本控制同等重要）：开发/测试过程**不得**为验证流程而调用真实 AI。三档零成本选择见 `analysis/README.md#开发成本纪律`——采集层回归用 `--no-ai`，全流程（含 prompt 渲染/schema 校验/评分/归档）用 `--ai-stub`（桩产物在 `analysis/ai/stub_outputs/`，报告不落 `reports/`），流水线联调用 `--mock`；真实 AI 只在 prompt/schema 变更后对小仓库抽检。另有单任务 AI 预算硬上界 `config.MAX_TASK_AI_COST_USD`（$5，触顶后剩余 AI 子任务计划跳过）
