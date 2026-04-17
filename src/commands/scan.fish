# scan.fish — Scan cloned repos for anomalies

source (dirname (status -f))/../common.fish

function cmd_scan
    require_gh
    or return 1

    init_log_session "scan" ""

    set -l root (get_project_root)
    set -l repos_dir "$root/repos"

    if not test -d "$repos_dir"
        log_warn "No repos directory found."
        return 0
    end

    set -l all_repos (scan_repos)
    if test (count $all_repos) -eq 0
        log_warn "No cloned repositories found."
        return 0
    end

    log_info "Scanning "(count $all_repos)" repositories for anomalies..."
    echo

    set -l deleted_repos
    set -l renamed_repos
    set -l corrupted_dirs
    set -l healthy_count 0

    for full_name in $all_repos
        set -l parts (string split '/' $full_name)
        set -l repo_path ""
        if test (count $parts) -eq 2
            set repo_path "$repos_dir/$parts[1]/$parts[2]"
        else
            set repo_path "$repos_dir/$parts[1]"
        end

        printf "%-50s" "$full_name"

        # Check 1: Is it a valid git repository?
        if not git -C "$repo_path" rev-parse --is-inside-work-tree >/dev/null 2>&1
            set -a corrupted_dirs "$full_name"
            set_color red
            echo "corrupted (not a valid git repo)"
            set_color normal
            log_error_raw "scan '$full_name'" "corrupted: not a valid git repository at $repo_path"
            continue
        end

        # Check 2: Get remote URL and parse org/repo
        set -l remote_url (git -C "$repo_path" remote get-url origin 2>/dev/null)
        if test -z "$remote_url"
            set -a corrupted_dirs "$full_name"
            set_color red
            echo "corrupted (no remote 'origin')"
            set_color normal
            log_error_raw "scan '$full_name'" "corrupted: no remote 'origin' configured"
            continue
        end

        # Parse org and repo name from URL
        set -l remote_org (echo "$remote_url" | string replace -r '.+github.com[/:]([^/]+)/.+' '$1')
        set -l remote_repo (echo "$remote_url" | string replace -r '.+github.com[/:][^/]+/(.+?)(\.git)?$' '$1')

        if test -z "$remote_org" -o -z "$remote_repo"
            set -a corrupted_dirs "$full_name"
            set_color red
            echo "corrupted (cannot parse remote URL)"
            set_color normal
            log_error_raw "scan '$full_name'" "corrupted: cannot parse remote URL: $remote_url"
            continue
        end

        # Check 3: Query GitHub API to see if repo still exists
        set -l api_output (gh api "repos/$remote_org/$remote_repo" --jq '{name: .name, full_name: .full_name}' 2>&1)
        if test $status -ne 0
            set -a deleted_repos "$full_name"
            set_color red
            echo "deleted or inaccessible on GitHub"
            set_color normal
            log_error_raw "scan '$full_name'" "deleted or inaccessible on GitHub (remote: $remote_url, api: $api_output)"
            continue
        end

        # Check 4: Has the repo been renamed?
        set -l github_name (echo "$api_output" | jq -r '.name')
        if test "$github_name" != "$remote_repo"
            set -a renamed_repos "$full_name|$github_name|$remote_repo|$remote_org"
            set_color yellow
            echo "renamed on GitHub (→ $github_name)"
            set_color normal
            log_error_raw "scan '$full_name'" "renamed on GitHub: local dir '$remote_repo' → GitHub '$github_name'"
            continue
        end

        set_color green
        echo "ok"
        set_color normal
        set healthy_count (math $healthy_count + 1)
    end

    echo
    log_info "Scan results: "(count $all_repos)" total, $healthy_count healthy, "(count $deleted_repos)" deleted, "(count $renamed_repos)" renamed, "(count $corrupted_dirs)" corrupted"

    # Report deleted repos
    if test (count $deleted_repos) -gt 0
        echo
        set_color red
        echo "Deleted repos (only report, not deleted locally):"
        set_color normal
        for repo in $deleted_repos
            echo "  - $repo"
        end
        log_info "Consider removing these locally if they are no longer needed."
    end

    # Handle renamed repos
    if test (count $renamed_repos) -gt 0
        echo
        set_color yellow
        echo "Renamed repos on GitHub (prompting to rename locally):"
        set_color normal

        for entry in $renamed_repos
            set -l local_path (string split '|' $entry)[1]
            set -l new_name (string split '|' $entry)[2]
            set -l old_name (string split '|' $entry)[3]
            set -l remote_org (string split '|' $entry)[4]

            set -l parts (string split '/' $local_path)
            set -l old_dir ""
            set -l new_dir ""
            if test (count $parts) -eq 2
                set old_dir "$repos_dir/$parts[1]/$old_name"
                set new_dir "$repos_dir/$parts[1]/$new_name"
            else
                set old_dir "$repos_dir/$old_name"
                set new_dir "$repos_dir/$new_name"
            end

            echo "  $local_path → $new_name"

            printf "    Rename local directory? [y/N]: "
            set -l answer
            read answer
            if string match -qi 'y*' "$answer"
                if test -d "$new_dir"
                    log_warn "  Directory '$new_name' already exists, skipping"
                else
                    mv "$old_dir" "$new_dir"
                    if test $status -eq 0
                        log_success "  Renamed: $old_name → $new_name"
                        git -C "$new_dir" remote set-url origin "https://github.com/$remote_org/$new_name.git" 2>/dev/null
                        if test -f "$new_dir/.git/config"
                            sed -i '' "s|$old_name|$new_name|g" "$new_dir/.git/config"
                        end
                    else
                        log_error "  Failed to rename '$old_name'"
                    end
                end
            else
                log_info "  Skipped rename for '$local_path'"
            end
        end
    end

    if test (count $deleted_repos) -gt 0 -o (count $renamed_repos) -gt 0 -o (count $corrupted_dirs) -gt 0
        log_info "Details written to "(get_error_log_path)
        return 1
    end
end

for arg in $argv
    switch $arg
        case '-h' '--help' 'help'
            echo "Usage: fish src/main.fish scan"
            echo
            echo "Scan cloned repositories for anomalies:"
            echo "  - Repos deleted or renamed on GitHub"
            echo "  - Corrupted or non-git directories"
            echo
            echo "For renamed repos, you'll be prompted to rename the local directory."
            exit 0
        case '-*'
            log_error "Unknown option: $arg"
            exit 1
    end
end

cmd_scan
