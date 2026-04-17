# Organization Repository Utility

A Fish shell-based CLI tool for managing GitHub organization repositories, powered entirely by Fish shell and `jq`.

## Features

- **Batch Clone** — Clone multiple repositories from an organization with filtering by name or pattern
- **Sync Updates** — Pull remote updates across all cloned repos with dry-run preview support
- **Export Info** — Export repository metadata (size, last update, visibility, etc.) as JSON
- **Scan Anomalies** — Detect repos that were deleted, renamed, or corrupted locally

## Requirements

- [Fish shell](https://fishshell.com/)
- [GitHub CLI (`gh`)](https://cli.github.com/) — authenticated via `gh auth login`
- [jq](https://jqlang.github.io/jq/) — for JSON parsing (`brew install jq`)

## Usage

```fish
# Interactive menu
fish src/main.fish

# CLI commands
fish src/main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]
fish src/main.fish sync [--dry-run]
fish src/main.fish export [--org <org>] [--output <file>] [--local]
fish src/main.fish scan                    # check for deleted, renamed, corrupted repos
```

## Directory Structure

- `src/` — Fish shell scripts
- `repos/` — Cloned repositories, organized by organization name (`repos/org-name/repo-name/`)
- `logs/errors.log` — Error details from all command executions (append-only)
