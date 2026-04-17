# clone.fish — Batch clone repositories from a GitHub organization

source (dirname (status -f))/../common.fish

function cmd_clone --argument-names org pattern repo_list
    require_gh
    or return 1

    if test -z "$org"
        log_error "Usage: clone <org> [--pattern <glob>] [--list <repo1,repo2>]"
        return 1
    end

    init_log_session "clone" "$org (pattern=$pattern list=$repo_list)"

    set -l root (get_project_root)
    set -l repos_dir "$root/repos/$org"

    mkdir -p "$repos_dir"

    # Fetch repo names from GitHub API
    set -l api_output (gh api "orgs/$org/repos" --paginate --jq '.[].name' 2>&1)
    if test $status -ne 0
        log_error "Failed to fetch repos for org '$org'" $api_output
        return 1
    end

    # Apply filters
    set -l target_repos

    if test -n "$repo_list"
        for name in (string split , "$repo_list")
            set name (string trim $name)
            if contains "$name" $api_output
                set -a target_repos "$name"
            else
                log_warn "Repository '$name' not found in org '$org', skipping"
            end
        end
    else if test -n "$pattern"
        for name in $api_output
            if string match -r "$pattern" "$name" >/dev/null 2>&1
                set -a target_repos "$name"
            end
        end
    else
        set target_repos $api_output
    end

    if test (count $target_repos) -eq 0
        log_warn "No repositories matched the filter criteria"
        return 0
    end

    log_info "Cloning "(count $target_repos)" repositories from '$org'..."
    echo

    set -l skip_count 0
    set -l cloning_repos
    set -l tmp_dir (mktemp -d)

    # Clone in parallel, capturing stderr to temp files
    for repo in $target_repos
        if git -C "$repos_dir/$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1
            log_warn "Skipping '$repo' -- already cloned"
            set skip_count (math $skip_count + 1)
            continue
        end

        set -a cloning_repos "$repo"
        git clone "https://github.com/$org/$repo.git" "$repos_dir/$repo" 2>"$tmp_dir/$repo.err" &
    end

    # Wait for all background jobs to finish
    wait

    # Check results and log errors
    set -l success_count 0
    set -l fail_count 0

    for repo in $cloning_repos
        if git -C "$repos_dir/$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1
            set success_count (math $success_count + 1)
            # Clean up temp file on success
            rm -f "$tmp_dir/$repo.err"
        else
            set fail_count (math $fail_count + 1)
            # Read and log stderr
            set -l err_output ""
            if test -f "$tmp_dir/$repo.err"
                set err_output (cat "$tmp_dir/$repo.err")
                log_error_raw "clone '$repo'" $err_output
                rm -f "$tmp_dir/$repo.err"
            end
        end
    end

    # Clean up temp dir
    rmdir "$tmp_dir" 2>/dev/null

    set -l total (count $target_repos)
    echo
    log_info "Clone summary: $total total, $success_count succeeded, $skip_count skipped, $fail_count failed"
    if test $fail_count -gt 0
        log_info "Details written to "(get_error_log_path)
        return 1
    end
end

# Parse arguments
set -l org ""
set -l pattern ""
set -l repo_list ""

for i in (seq 1 (count $argv))
    switch $argv[$i]
        case '--pattern'
            set i (math $i + 1)
            if test $i -le (count $argv)
                set pattern $argv[$i]
            end
        case '--list'
            set i (math $i + 1)
            if test $i -le (count $argv)
                set repo_list $argv[$i]
            end
        case '-*'
            log_error "Unknown option: $argv[$i]"
            exit 1
        case '*'
            if test -z "$org"
                set org $argv[$i]
            end
    end
end

cmd_clone "$org" "$pattern" "$repo_list"
