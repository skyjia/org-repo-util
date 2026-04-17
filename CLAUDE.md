# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**org-repo-util** is a Fish shell-based CLI tool for managing GitHub organization repositories. It supports batch cloning repos, syncing updates, and exporting metadata as JSON. Pure Fish shell + `jq`, no Python.

## Commands

```fish
# Interactive menu
fish src/main.fish

# Batch clone
fish src/main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]

# Sync updates
fish src/main.fish sync [--dry-run]

# Export repo metadata as JSON
fish src/main.fish export [--org <org>] [--output <file>] [--local]

# Scan for deleted, renamed, or corrupted repos
fish src/main.fish scan

# Help
fish src/main.fish --help
```

## Project Structure

- `src/main.fish` — CLI entry point (arg parsing + interactive menu)
- `src/common.fish` — Shared utilities (logging, repo scanning, prereq checks)
- `src/commands/clone.fish` — Batch clone with pattern filtering and parallel execution
- `src/commands/sync.fish` — Sync all cloned repos (pull --rebase) with dry-run support
- `src/commands/export.fish` — Export repo metadata as JSON via `gh api` + `jq`
- `src/commands/scan.fish` — Scan for deleted, renamed, or corrupted repos
- `repos/<org>/<repo>/` — Cloned repositories organized by organization
- `logs/errors.log` — Append-only error log (session headers + error details with raw stderr)

## Requirements

- Fish shell
- GitHub CLI (`gh`), authenticated via `gh auth login`
- `jq` for JSON processing (`brew install jq`)

## Architecture Notes

- Pure Fish shell — no Python dependencies
- `gh api` for all GitHub API calls, `jq` for JSON parsing/filtering
- Clone runs in parallel via Fish job control; sync and export run sequentially
- Error details are written to `logs/errors.log` (append-only), terminal shows summary only
- Batch operations continue on failure; failed clones captured via per-repo temp stderr files
