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
