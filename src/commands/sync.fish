# sync.fish — Sync all cloned repositories with their remotes

source (dirname (status -f))/../common.fish

function cmd_sync --argument-names dry_run jobs
    require_gh
    or return 1

    init_log_session "sync" "--dry-run=$dry_run --jobs=$jobs"

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

    # Create temp directory for counters and lock
    set -l temp_dir (mktemp -d)
    set -l lock_file "$temp_dir/print.lock"
    set -l success_file "$temp_dir/success.txt"
    set -l uptodate_file "$temp_dir/uptodate.txt"
    set -l fail_file "$temp_dir/fail.txt"

    if test "$dry_run" = "true"
        log_info "DRY RUN — showing what would be updated for "(count $repos)" repos (jobs: $jobs)"
        echo
    else
        log_info "Syncing "(count $repos)" repositories (jobs: $jobs)..."
        echo
    end

    set -l running 0

    for full_name in $repos
        set -l parts (string split '/' $full_name)
        set -l repo_path ""
        if test (count $parts) -eq 2
            set repo_path "$repos_dir/$parts[1]/$parts[2]"
        else
            set repo_path "$repos_dir/$parts[1]"
        end

        # Wait if we've reached max concurrent jobs
        if test $running -ge $jobs
            wait -n
            set running (math $running - 1)
        end

        # Launch background job - uses lock file for atomic printing
        fish -c '
            set -l full_name "'$full_name'"
            set -l repo_path "'$repo_path'"
            set -l dry_run "'$dry_run'"
            set -l lock_file "'$lock_file'"
            set -l success_file "'$success_file'"
            set -l uptodate_file "'$uptodate_file'"
            set -l fail_file "'$fail_file'"
            set -l log_path "'(get_error_log_path)'"

            set -l status_text ""
            set -l status_type ""

            if test "$dry_run" = "true"
                set -l fetch_output (git -C "$repo_path" fetch --dry-run 2>&1)
                set -l git_status $status
                if test $git_status -ne 0
                    set status_text "failed"
                    set status_type "fail"
                    echo "[$(date "+%Y-%m-%d %H:%M:%S")] ERROR $full_name fetch failed" >> "$log_path"
                    echo "  $fetch_output" >> "$log_path"
                else if string match -q "Already up to date." "$fetch_output"
                    set status_text "up to date"
                    set status_type "uptodate"
                else
                    set status_text "would pull updates"
                    set status_type "success"
                end
            else
                set -l pull_output (git -C "$repo_path" pull --rebase 2>&1)
                set -l git_status $status
                if test $git_status -ne 0
                    set status_text "failed"
                    set status_type "fail"
                    echo "[$(date "+%Y-%m-%d %H:%M:%S")] ERROR $full_name pull failed" >> "$log_path"
                    echo "  $pull_output" >> "$log_path"
                else if string match -q "Already up to date." "$pull_output"
                    set status_text "up to date"
                    set status_type "uptodate"
                else
                    set status_text "updated"
                    set status_type "success"
                end
            end

            # Acquire lock for atomic printing
            while test -f "$lock_file"
                sleep 0.05
            end
            touch "$lock_file"

            # Print complete line with color
            switch $status_type
                case "fail"
                    set_color red
                    printf "%-40s %s\n" "$full_name" "$status_text"
                    set_color normal
                case "uptodate"
                    set_color yellow
                    printf "%-40s %s\n" "$full_name" "$status_text"
                    set_color normal
                case "success"
                    if test "$dry_run" = "true"
                        set_color cyan
                    else
                        set_color green
                    end
                    printf "%-40s %s\n" "$full_name" "$status_text"
                    set_color normal
            end

            # Release lock
            rm "$lock_file"

            # Record status for summary
            switch $status_type
                case "success"
                    echo "1" >> "$success_file"
                case "uptodate"
                    echo "1" >> "$uptodate_file"
                case "fail"
                    echo "1" >> "$fail_file"
            end
        ' &
        set running (math $running + 1)
    end

    # Wait for all remaining background jobs
    wait

    # Count results from files
    set -l success_count 0
    set -l up_to_date_count 0
    set -l fail_count 0

    if test -f "$success_file"
        set success_count (wc -l < "$success_file" | string trim)
    end
    if test -f "$uptodate_file"
        set up_to_date_count (wc -l < "$uptodate_file" | string trim)
    end
    if test -f "$fail_file"
        set fail_count (wc -l < "$fail_file" | string trim)
    end

    # Cleanup temp directory
    rm -rf "$temp_dir"

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
set -l jobs 1

for arg in $argv
    switch $arg
        case '--dry-run'
            set dry_run "true"
        case '-j' '--jobs'
            # Next argument should be the number
        case '*'
            # Check if previous arg was -j or --jobs
            if set -q prev_arg
                switch $prev_arg
                    case '-j' '--jobs'
                        set jobs $arg
                end
            end
    end
    set prev_arg $arg
end

# Handle --jobs=N and -jN formats
for arg in $argv
    if string match -qr -- '^--jobs=(\d+)$' $arg
        set jobs (string replace -r -- '^--jobs=(\d+)$' '$1' $arg)
    end
    if string match -qr -- '^-j(\d+)$' $arg
        set jobs (string replace -r -- '^-j(\d+)$' '$1' $arg)
    end
end

cmd_sync "$dry_run" "$jobs"