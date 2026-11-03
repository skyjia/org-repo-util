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
fish src/main.fish sync [--dry-run] [-j N|--jobs N]
fish src/main.fish export [--org <org>] [--output <file>] [--local]
fish src/main.fish scan                    # check for deleted, renamed, corrupted repos
```

### Sync Options

- `--dry-run` — Preview what would be updated without pulling
- `-j N` or `--jobs N` — Number of concurrent sync jobs (default: 1)

When using parallel sync (`-j N > 1`), each repository's sync result is displayed in real-time as it completes, with color-coded status:
- **Yellow** — up to date
- **Green** — updated
- **Red** — failed

## Directory Structure

- `src/` — Fish shell scripts
- `repos/` — Cloned repositories, organized by organization name (`repos/org-name/repo-name/`)
- `logs/errors.log` — Error details from all command executions (append-only)
