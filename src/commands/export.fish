# export.fish — Export repository metadata as JSON

source (dirname (status -f))/../common.fish

function cmd_export --argument-names org output filter_local
    require_gh
    require_jq

    set -l org_label "$org"; if test -z "$org_label"; set org_label "auto"; end
    init_log_session "export" "--org=$org_label --local=$filter_local"

    set -l root (get_project_root)

    # If no org specified, list available orgs or error
    if test -z "$org"
        set -l orgs (list_orgs)
        if test (count $orgs) -eq 0
            log_error "Usage: export --org <org-name>"
            log_info "No orgs found. Clone some repos first."
            return 1
        else if test (count $orgs) -eq 1
            set org $orgs[1]
            log_info "Using org: $org"
        else
            log_error "Multiple orgs found. Specify --org: "(string join ', ' $orgs)
            return 1
        end
    end

    set -l tmp_err (mktemp)
    set -l tmp_out (mktemp)

    if test "$filter_local" = "true"
        set -l local_names (scan_repos | string match "$org/*" | string replace "$org/" "")

        if test (count $local_names) -eq 0
            log_warn "No locally cloned repos found for org '$org'"
            rm -f "$tmp_err" "$tmp_out"
            return 0
        end

        set -l local_json (printf '%s\n' $local_names | jq -R . | jq -s .)
        gh api "orgs/$org/repos" --paginate 2>"$tmp_err" \
            | jq --argjson local "$local_json" \
                '[.[] | select(.name as $n | $local | index($n)) | {name, visibility, size, pushed_at, description, archived, clone_url, ssh_url, language, stargazers_count, forks_count}]' \
            > "$tmp_out"
    else
        gh api "orgs/$org/repos" --paginate 2>"$tmp_err" \
            | jq '[.[] | {name, visibility, size, pushed_at, description, archived, clone_url, ssh_url, language, stargazers_count, forks_count}]' \
            > "$tmp_out"
    end

    if test $status -ne 0
        set -l err_output (cat "$tmp_err")
        log_error "Failed to fetch repos for org '$org'" $err_output
        rm -f "$tmp_err" "$tmp_out"
        return 1
    end

    if test -n "$output"
        mv "$tmp_out" "$output"
        log_success "Exported to $output"
    else
        cat "$tmp_out"
        rm -f "$tmp_out"
    end

    rm -f "$tmp_err"
end

# Parse arguments
set -l org ""
set -l output ""
set -l filter_local "false"

for i in (seq 1 (count $argv))
    switch $argv[$i]
        case '--org'
            set i (math $i + 1)
            if test $i -le (count $argv)
                set org $argv[$i]
            end
        case '--output'
            set i (math $i + 1)
            if test $i -le (count $argv)
                set output $argv[$i]
            end
        case '--local'
            set filter_local "true"
        case '-*'
            log_error "Unknown option: $argv[$i]"
            exit 1
        case '*'
            if test -z "$org"
                set org $argv[$i]
            end
    end
end

cmd_export "$org" "$output" "$filter_local"
