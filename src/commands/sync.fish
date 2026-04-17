# sync.fish — Sync all cloned repositories with their remotes

source (dirname (status -f))/../common.fish

function cmd_sync --argument-names dry_run
    require_gh
    or return 1

    init_log_session "sync" "--dry-run=$dry_run"

    set -l root (get_project_root)
    set -l repos_dir "$root/repos"

    if not test -d "$repos_dir"
        log_warn "No repos directory found. Clone some repos first."
        return 0
    end

    set -l repos (scan_repos)
    if test (count $repos) -eq 0
        log_warn "No cloned repositories found. Clone some repos first."
        return 0
    end

    if test "$dry_run" = "true"
        log_info "DRY RUN — showing what would be updated for "(count $repos)" repos"
        echo
    else
        log_info "Syncing "(count $repos)" repositories..."
        echo
    end

    set -l success_count 0
    set -l up_to_date_count 0
    set -l fail_count 0

    for full_name in $repos
        set -l parts (string split '/' $full_name)
        set -l repo_path ""
        if test (count $parts) -eq 2
            set repo_path "$repos_dir/$parts[1]/$parts[2]"
        else
            set repo_path "$repos_dir/$parts[1]"
        end

        printf "%-40s" "$full_name"

        if test "$dry_run" = "true"
            set -l fetch_output (git -C "$repo_path" fetch --dry-run 2>&1)
            if test $status -ne 0
                log_error "$full_name fetch failed" $fetch_output
                set fail_count (math $fail_count + 1)
            else if string match -q 'Already up to date.' "$fetch_output"
                set_color yellow
                echo "up to date"
                set_color normal
                set up_to_date_count (math $up_to_date_count + 1)
            else
                set_color cyan
                echo "would pull updates"
                set_color normal
                set success_count (math $success_count + 1)
            end
        else
            set -l pull_output (git -C "$repo_path" pull --rebase 2>&1)
            if test $status -ne 0
                log_error "$full_name pull failed" $pull_output
                set fail_count (math $fail_count + 1)
            else if string match -q 'Already up to date.' "$pull_output"
                set_color yellow
                echo "up to date"
                set_color normal
                set up_to_date_count (math $up_to_date_count + 1)
            else
                set_color green
                echo "updated"
                set_color normal
                set success_count (math $success_count + 1)
            end
        end
    end

    echo
    if test "$dry_run" = "true"
        log_info "Dry run summary: "(count $repos)" total, $success_count would update, $up_to_date_count up to date, $fail_count would fail"
    else
        log_info "Sync summary: "(count $repos)" total, $success_count updated, $up_to_date_count up to date, $fail_count failed"
    end
    if test $fail_count -gt 0
        log_info "Details written to "(get_error_log_path)
    end
end

# Parse arguments
set -l dry_run "false"

for arg in $argv
    switch $arg
        case '--dry-run'
            set dry_run "true"
        case '-*'
            log_error "Unknown option: $arg"
            exit 1
    end
end

cmd_sync "$dry_run"
