# main.fish — CLI entry point: argument parsing + interactive menu

source (dirname (status -f))/common.fish

function print_usage
    echo "Usage:"
    echo "  fish main.fish clone <org> [--pattern <glob>] [--list <repo1,repo2>]"
    echo "  fish main.fish sync [--dry-run] [-j N|--jobs N]"
    echo "  fish main.fish export [--org <org>] [--output <file>] [--local] [--languages]"
    echo "  fish main.fish scan"
    echo "  fish main.fish                   # interactive menu"
    echo
    echo "Commands:"
    echo "  clone    Batch clone repos from a GitHub organization"
    echo "  sync     Pull updates for all cloned repositories"
    echo "  export   Export repository metadata as JSON"
    echo "  scan     Check repos for deleted, renamed, or corrupted repos"
    echo
    echo "Options:"
    echo "  --pattern   Glob pattern to filter repo names during clone"
    echo "  --list      Comma-separated list of specific repos to clone"
    echo "  --dry-run   Preview sync without pulling"
    echo "  -j, --jobs  Number of concurrent jobs for sync (default: 1)"
    echo "  --org       Organization name for export"
    echo "  --output    Write export to file instead of stdout"
    echo "  --local     Export only locally cloned repos"
    echo "  --languages Include language breakdown (slower, additional API calls)"
end

function show_menu
    echo
    set_color cyan
    echo "  Organization Repository Utility"
    set_color normal
    echo
    echo "  1. Clone repositories"
    echo "  2. Sync all repositories"
    echo "  3. Export repository info"
    echo "  4. Scan for anomalies"
    echo "  5. Quit"
    echo

    while true
        set_color cyan
        printf "  Choose [1-5]: "
        set_color normal

        set -l choice
        read choice

        switch $choice
            case 1
                handle_clone_menu
                break
            case 2
                handle_sync_menu
                break
            case 3
                handle_export_menu
                break
            case 4
                fish (dirname (status -f))/commands/scan.fish
                break
            case 5
                echo "  Bye!"
                return 0
            case '*'
                log_warn "Invalid choice"
        end
    end
end

function handle_clone_menu
    echo
    printf "  Organization name: "
    set -l org
    read org

    if test -z "$org"
        log_error "Organization name is required"
        return 1
    end

    printf "  Filter pattern (empty for all): "
    set -l pattern
    read pattern

    set -l cmd "fish (dirname (status -f))/commands/clone.fish $org"
    if test -n "$pattern"
        set cmd "$cmd --pattern '$pattern'"
    end

    eval $cmd
end

function handle_sync_menu
    echo
    printf "  Dry run? [y/N]: "
    set -l dry
    read dry

    printf "  Concurrent jobs [1]: "
    set -l jobs
    read jobs
    if test -z "$jobs"
        set jobs 1
    end

    set -l cmd "fish (dirname (status -f))/commands/sync.fish"
    if string match -qi 'y*' "$dry"
        set cmd "$cmd --dry-run"
    end
    set cmd "$cmd --jobs $jobs"

    eval $cmd
end

function handle_export_menu
    echo
    set -l orgs (list_orgs)
    if test (count $orgs) -gt 0
        echo "  Available orgs: "(string join ', ' $orgs)
    end

    printf "  Organization name: "
    set -l org
    read org

    if test -z "$org"
        log_error "Organization name is required"
        return 1
    end

    printf "  Output file (empty for stdout): "
    set -l output
    read output

    printf "  Only local repos? [y/N]: "
    set -l local
    read local

    printf "  Include language breakdown? [y/N]: "
    set -l languages
    read languages

    set -l cmd "fish (dirname (status -f))/commands/export.fish --org $org"
    if test -n "$output"
        set cmd "$cmd --output '$output'"
    end
    if string match -qi 'y*' "$local"
        set cmd "$cmd --local"
    end
    if string match -qi 'y*' "$languages"
        set cmd "$cmd --languages"
    end

    eval $cmd
end

# ---- Main entry ----

if test (count $argv) -eq 0
    show_menu
    exit $status
end

set -l command $argv[1]

switch $command
    case 'clone'
        fish (dirname (status -f))/commands/clone.fish $argv[2..-1]
    case 'sync'
        fish (dirname (status -f))/commands/sync.fish $argv[2..-1]
    case 'export'
        fish (dirname (status -f))/commands/export.fish $argv[2..-1]
    case 'scan'
        fish (dirname (status -f))/commands/scan.fish $argv[2..-1]
    case '-h' '--help' 'help'
        print_usage
    case '*'
        log_error "Unknown command: $command"
        print_usage
        exit 1
end
