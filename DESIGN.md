# Design Document

## Overview

A Fish shell-based CLI tool for batch-managing GitHub organization repositories. Uses `gh` CLI for authentication and API calls, `jq` for JSON processing, and Fish shell for all glue logic and user interaction.

## Architecture

### Directory Structure

```
org-repo-util/
├── src/
│   ├── main.fish              # CLI entry point: arg parsing + interactive menu
│   ├── common.fish            # Shared utilities: logging, repo scanning, color output
│   ├── commands/
│   │   ├── clone.fish         # Batch clone: fetch org repo list, filter, parallel clone
│   │   ├── sync.fish          # Sync: pull rebase across all repos in repos/
│   │   ├── export.fish        # Export: gather metadata, output as JSON
│   │   └── scan.fish          # Scan: detect deleted, renamed, or corrupted repos
├── repos/
│   └── <org-name>/
│       └── <repo-name>/       # Cloned repositories
├── logs/
│   └── errors.log             # Append-only error log from all command executions
└── README.md
```

### Component Responsibilities

#### `main.fish` — Entry Point

- Parses CLI arguments (`clone`, `sync`, `export` + flags)
- If no arguments provided, displays interactive menu
- Routes to the appropriate command script
- Validates prerequisites: `fish`, `gh` authenticated, `jq` available

#### `common.fish` — Shared Utilities

- `log_info`, `log_warn`, `log_error`, `log_success` — Colorized terminal output
- `scan_repos` — Scans `repos/<org>/` to discover locally cloned repos
- `get_project_root` — Resolves project root from any source file path
- `require_gh` — Ensures `gh` is installed and authenticated
- `require_jq` — Ensures `jq` is installed
- `filter_repos` — Filters repo list by regex pattern

#### `commands/clone.fish` — Batch Clone

- Accepts: `<org>`, optional `--pattern <glob>`, optional `--list <repo1,repo2,...>`
- Calls `gh api orgs/<org>/repos --paginate --jq '.[].name'` to fetch repo list
- Applies filters (pattern or explicit list)
- Uses Fish job control (`&` + `wait`) for parallel cloning
- Clones into `repos/<org>/<repo-name>/`
- Skips repos that already exist locally
- Uses `git rev-parse --is-inside-work-tree` for robust clone validation
- Errors are logged to terminal and execution continues

#### `commands/sync.fish` — Sync Updates

- Scans `repos/` for all cloned repositories
- `--dry-run` mode: shows what would be pulled for each repo without executing
- Default mode: runs `git pull --rebase` on each repo
- Reports per-repo status: up-to-date, updated, or failed

#### `commands/export.fish` — Export Repo Info

- Accepts: optional `--org <org>`, optional `--output <file>`, optional `--local`
- Calls `gh api orgs/<org>/repos --paginate` for raw JSON
- Pipes through `jq` to extract and format fields
- Collects: name, description, size, visibility, last push date, clone URL, language, stars, forks
- Outputs JSON to stdout or `--output` file
- `--local` flag filters to only locally cloned repos via `jq --argjson`

#### `commands/scan.fish` — Scan for Anomalies

- Iterates all repos found by `scan_repos`
- For each repo:
  1. Checks if it's a valid git repository (`git rev-parse --is-inside-work-tree`)
  2. Extracts remote URL and parses org/repo name
  3. Calls `gh api repos/<org>/<repo>` to verify it exists on GitHub
  4. Compares GitHub repo name with local dir name to detect renames
- Detects: deleted repos, renamed repos, corrupted `.git` dirs, missing remotes
- For renamed repos: prompts user to rename local directory (auto-updates git remote + config)
- For deleted repos: reports only, does not delete locally
- Results written to `logs/errors.log` with full details

## Data Flow

```
User → main.fish (parse args / menu)
         ↓
    commands/*.fish (orchestration)
         ↓
    gh CLI (GitHub API)
         ↓
    jq (JSON processing)
         ↓
    repos/<org>/<repo>/ (file system operations)
```

## Error Handling

- All commands write a session header to `logs/errors.log` at start (timestamp + command + args)
- Errors are written to the log file with timestamp, command context, and raw stderr output
- Terminal only shows summary info (e.g. "1 succeeded, 2 failed, details in logs/errors.log")
- `log_error` function accepts an optional second argument for detailed error text written to log
- `git clone` stderr is captured per-repo via temp files and written to log on failure
- Batch operations continue on failure; final summary includes error count and log file path

## Parallel Execution

- Clone uses Fish's built-in job control: `git clone ... &` followed by `wait`
- Sync and export run sequentially (safety: avoid concurrent git operations)
