# common.fish — Shared utilities

function log_info --description 'Print info message'
    set_color blue
    echo "[INFO]  $argv"
    set_color normal
end

function log_warn --description 'Print warning message'
    set_color yellow
    echo "[WARN]  $argv"
    set_color normal
end

function log_error --description 'Print error message to terminal and log file' --argument-names message detail
    set_color red
    if test -n "$detail"
        echo "[ERROR]  $message (see logs/errors.log for details)"
    else
        echo "[ERROR]  $message"
    end
    set_color normal

    # Write to log file
    set -l timestamp (date '+%Y-%m-%d %H:%M:%S')
    if test -n "$detail"
        echo "[$timestamp] ERROR $message" >> (get_error_log_path)
        echo "  $detail" >> (get_error_log_path)
    else
        echo "[$timestamp] ERROR $message" >> (get_error_log_path)
    end
end

function log_success --description 'Print success message'
    set_color green
    echo "[OK]  $argv"
    set_color normal
end

function get_error_log_path --description 'Return the path to the error log file'
    set -l root (get_project_root)
    echo "$root/logs/errors.log"
end

function init_log_session --description 'Initialize a new log session entry for a command' --argument-names command args
    set -l timestamp (date '+%Y-%m-%d %H:%M:%S')
    set -l log_path (get_error_log_path)

    # Ensure logs directory exists
    mkdir -p (dirname $log_path)

    # Blank line between sessions
    echo "" >> $log_path
    echo "[$timestamp] $command $args" >> $log_path
end

function log_error_raw --description 'Write raw error output to log file' --argument-names command detail
    set -l timestamp (date '+%Y-%m-%d %H:%M:%S')
    set -l log_path (get_error_log_path)
    mkdir -p (dirname $log_path)

    echo "[$timestamp] ERROR $command: $detail" >> $log_path
end

function require_gh --description 'Check gh CLI is installed and authenticated'
    if not command -sq gh
        log_error "gh CLI is not installed. Install from https://cli.github.com/"
        return 1
    end

    if not gh auth status >/dev/null 2>&1
        log_error "Not authenticated with gh. Run: gh auth login"
        return 1
    end
end

function require_jq --description 'Check jq is installed'
    if not command -sq jq
        log_error "jq is not installed. Install with: brew install jq"
        return 1
    end
end

function get_project_root --description 'Return the project root directory'
    set -l this_file (realpath (status -f))
    set -l dir (dirname $this_file)
    if test (basename $dir) = "commands"
        dirname (dirname $dir)
    else if test (basename $dir) = "src"
        dirname $dir
    else
        echo $dir
    end
end

function scan_repos --description 'Scan repos/ for cloned git repos, supports both flat and org/repo structure'
    set -l root (get_project_root)
    set -l repos_dir "$root/repos"

    if not test -d "$repos_dir"
        return
    end

    # Scan flat repos directly under repos/ (repos/<repo>/.git)
    for repo_dir in "$repos_dir"/*/
        if not test -d "$repo_dir"
            continue
        end
        if test -d "$repo_dir/.git"
            set -l repo (basename "$repo_dir")
            if test (count (find "$repo_dir" -maxdepth 1 -mindepth 1 -type d -not -name '.git' 2>/dev/null)) -gt 0
                continue
            end
            echo "$repo"
        end
    end

    # Scan org-structured repos (repos/<org>/<repo>/.git)
    for org_dir in "$repos_dir"/*/
        if not test -d "$org_dir"
            continue
        end
        set -l org (basename "$org_dir")
        if test -d "$org_dir/.git"
            continue
        end
        for repo_dir in "$org_dir"/*/
            if test -d "$repo_dir/.git"
                set -l repo (basename "$repo_dir")
                echo "$org/$repo"
            end
        end
    end
end

function filter_repos --description 'Filter repo list by glob pattern' --argument-names repos pattern
    for repo in $repos
        if string match -r "$pattern" "$repo" >/dev/null 2>&1
            echo "$repo"
        end
    end
end

function list_orgs --description 'List organizations that have cloned repos'
    set -l root (get_project_root)
    set -l repos_dir "$root/repos"

    if not test -d "$repos_dir"
        return
    end

    for org_dir in "$repos_dir"/*/
        if test -d "$org_dir"
            basename "$org_dir"
        end
    end
end
