#!/usr/bin/env bash
# Shared lexical identity checks. No network, Git, or shell evaluation of data.
github_error() {
    printf 'ERROR: GitHub %s\n' "$1" >&2
    return 1
}

github_repository_input() {
    [[ $# == 2 && "$1" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ && "$1" != *- && "$1" != *--* &&
       "$2" =~ ^[A-Za-z0-9_.-]{1,100}$ && "$2" != . && "$2" != .. ]] || {
        github_error 'explicit valid owner and repository are required'; return 1;
    }
}

github_issue_input() {
    [[ $# == 3 ]] || { github_error 'owner, repository and issue number are required'; return 1; }
    github_repository_input "$1" "$2" || return 1
    # Bound integers to exact jq/JSON numeric representation; no leading zeros.
    [[ "$3" =~ ^[1-9][0-9]{0,14}$ ]] || {
        github_error 'issue number must be a positive integer of at most 15 digits'; return 1;
    }
}

github_text_input() {
    [[ $# == 1 && "$1" =~ [^[:space:]] ]] || {
        github_error 'nonempty meaningful text is required'; return 1;
    }
}

# Output canonical owner/repo only. Credential-bearing URLs are never printed.
# get-url callers must supply Git's expanded effective URL, not raw config.
github_remote_identity() {
    local url="$1" path='' authority=''
    case "$url" in
        https://*)
            path="${url#https://}"; authority="${path%%/*}"
            [[ "${authority##*@}" == github.com ]] || return 1
            [[ "$path" == */* ]] || return 1
            path="${path#*/}"
            ;;
        git@github.com:*) path="${url#git@github.com:}" ;;
        ssh://git@github.com/*) path="${url#ssh://git@github.com/}" ;;
        ssh://git@github.com:22/*) path="${url#ssh://git@github.com:22/}" ;;
        *) return 1 ;;
    esac
    path="${path%.git}"
    [[ "$path" == */* && "${path#*/}" != */* ]] || return 1
    github_repository_input "${path%%/*}" "${path#*/}" 2>/dev/null || return 1
    printf '%s\n' "${path,,}"
}
