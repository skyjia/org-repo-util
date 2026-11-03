# export.fish — Export repository metadata as JSON

source (dirname (status -f))/../common.fish

function cmd_export --argument-names org output filter_local include_languages
    require_gh
    require_jq

    set -l org_label "$org"; if test -z "$org_label"; set org_label "auto"; end
    init_log_session "export" "--org=$org_label --local=$filter_local --languages=$include_languages"

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

    # Base fields to export
    set -l base_fields '{name, visibility, size, pushed_at, description, archived, clone_url, ssh_url, primary_language: .language, stargazers_count, forks_count}'

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
                "[.[] | select(.name as \$n | \$local | index(\$n)) | $base_fields]" \
            > "$tmp_out"
    else
        gh api "orgs/$org/repos" --paginate 2>"$tmp_err" \
            | jq "[.[] | $base_fields]" \
            > "$tmp_out"
    end

    if test $status -ne 0
        set -l err_output (cat "$tmp_err")
        log_error "Failed to fetch repos for org '$org'" $err_output
        rm -f "$tmp_err" "$tmp_out"
        return 1
    end

    # If --languages flag is set, fetch language breakdown for each repo
    if test "$include_languages" = "true"
        log_info "Fetching language breakdown for repositories..."
        set -l repos (jq -r '.[].name' "$tmp_out")
        set -l tmp_lang (mktemp)

        for repo in $repos
            printf "  %s..." "$repo"
            # Get language bytes from API
            set -l lang_bytes (gh api "repos/$org/$repo/languages" 2>/dev/null)
            if test $status -eq 0 -a -n "$lang_bytes"
                # Calculate percentages with 1 decimal place
                set -l lang_json (echo "$lang_bytes" | jq '
                    to_entries as $entries |
                    ($entries | map(.value) | add) as $total |
                    if $total > 0 then
                        [$entries[] | {(.key): ((.value / $total * 1000 | round) / 10)}] | add
                    else
                        {}
                    end
                ')
                # Merge languages into the repo entry
                jq --arg name "$repo" --argjson langs "$lang_json" \
                    '[.[] | if .name == $name then . + {languages: $langs} else . end]' \
                    "$tmp_out" > "$tmp_lang"
                mv "$tmp_lang" "$tmp_out"
                echo " done"
            else
                echo " skipped (no languages data)"
            end
        end

        rm -f "$tmp_lang"
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
set -l include_languages "false"

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
        case '--languages'
            set include_languages "true"
        case '-*'
            log_error "Unknown option: $argv[$i]"
            exit 1
        case '*'
            if test -z "$org"
                set org $argv[$i]
            end
    end
end

cmd_export "$org" "$output" "$filter_local" "$include_languages"
