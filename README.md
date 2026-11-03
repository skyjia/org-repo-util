# Organization Repository Utility

A Fish shell-based CLI tool for managing GitHub organization repositories, powered entirely by Fish shell and `jq`.

## Features

- **Batch Clone** — Clone multiple repositories from an organization with filtering by name or pattern (includes both public and private repos)
- **Sync Updates** — Pull remote updates across all cloned repos with dry-run preview and parallel execution support
- **Export Info** — Export repository metadata (size, last update, visibility, language, etc.) as JSON, with optional language breakdown
- **Scan Anomalies** — Detect repos that were deleted, renamed, or corrupted locally (with secondary verification to avoid false positives)

## Requirements

- [Fish shell](https://fishshell.com/)
- [GitHub CLI (`gh`)](https://cli.github.com/) — authenticated via `gh auth login`
  - For private repos, ensure your token has `repo` scope
- [jq](https://jqlang.github.io/jq/) — for JSON parsing (`brew install jq`)

## Usage

```fish
# Interactive menu
fish src/main.fish

# CLI commands
fish src/main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]
fish src/main.fish sync [--dry-run] [-j N|--jobs N]
fish src/main.fish export [--org <org>] [--output <file>] [--local] [--languages]
fish src/main.fish scan
```

### Clone

Batch clone repositories from a GitHub organization.

```fish
fish src/main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]
```

**Options:**
- `<org>` — Organization name (required)
- `--pattern <glob>` — Filter repos by name pattern (e.g., `--pattern "api-*"`)
- `--list <repo1,repo2>` — Clone specific repos (comma-separated)

**Notes:**
- Fetches all repos the authenticated user has access to (public + private)
- Skips repos that are already cloned locally
- Clones run in parallel for better performance

### Sync

Pull updates for all cloned repositories.

```fish
fish src/main.fish sync [--dry-run] [-j N|--jobs N]
```

**Options:**
- `--dry-run` — Preview what would be updated without pulling
- `-j N` or `--jobs N` — Number of concurrent sync jobs (default: 1)

**Output:**
When using parallel sync (`-j N > 1`), each repository's sync result is displayed in real-time:
- **Yellow** — up to date
- **Green** — updated
- **Red** — failed

### Export

Export repository metadata as JSON.

```fish
fish src/main.fish export [--org <org>] [--output <file>] [--local] [--languages]
```

**Options:**
- `--org <org>` — Organization name (auto-detected if only one org exists)
- `--output <file>` — Write to file instead of stdout
- `--local` — Export only locally cloned repos
- `--languages` — Include language breakdown (slower, requires additional API calls per repo)

**Exported Fields:**
```json
{
  "name": "repo-name",
  "visibility": "private",
  "archived": false,
  "size": 12345,
  "pushed_at": "2024-01-15T10:30:00Z",
  "description": "Repository description",
  "clone_url": "https://github.com/org/repo.git",
  "ssh_url": "git@github.com:org/repo.git",
  "primary_language": "TypeScript",
  "stargazers_count": 42,
  "forks_count": 10,
  "languages": {
    "TypeScript": 75.5,
    "JavaScript": 20.3,
    "HTML": 4.2
  }
}
```

**Notes:**
- `languages` field only included when `--languages` flag is used
- Language percentages are rounded to 1 decimal place
- Using `--languages` makes one additional API call per repository

### Scan

Scan cloned repositories for anomalies.

```fish
fish src/main.fish scan
```

**Checks performed:**
1. **Valid git repository** — Detects corrupted or non-git directories
2. **Remote accessibility** — Verifies the repo still exists on GitHub (with secondary `git ls-remote` verification to avoid false positives from API issues)
3. **Renamed repos** — Detects if the repo was renamed on GitHub and prompts to rename locally
4. **Deleted repos** — Reports repos that no longer exist (only reported, not deleted locally)

**Output:**
- **Green** — ok (or ok with API unavailable but remote accessible)
- **Yellow** — renamed on GitHub (prompts for local rename)
- **Red** — deleted/inaccessible or corrupted

## Directory Structure

- `src/` — Fish shell scripts
  - `main.fish` — CLI entry point and interactive menu
  - `common.fish` — Shared utilities
  - `commands/` — Individual command implementations
- `repos/` — Cloned repositories, organized by organization name (`repos/org-name/repo-name/`)
- `logs/errors.log` — Error details from all command executions (append-only)

## Examples

```fish
# Clone all repos from an org
fish src/main.fish clone myorg

# Clone only repos matching a pattern
fish src/main.fish clone myorg --pattern "api-*"

# Clone specific repos
fish src/main.fish clone myorg --list "repo1,repo2,repo3"

# Sync all repos with 4 parallel jobs
fish src/main.fish sync -j 4

# Preview sync without pulling
fish src/main.fish sync --dry-run

# Export basic metadata
fish src/main.fish export --org myorg --output repos.json

# Export with language breakdown
fish src/main.fish export --org myorg --languages --output repos.json

# Export only locally cloned repos
fish src/main.fish export --org myorg --local

# Scan for anomalies
fish src/main.fish scan
```
