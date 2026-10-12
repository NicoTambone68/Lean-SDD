#!/usr/bin/env bash
# Helpers for the B executable entry points. Each entry point owns this scratch
# directory and EXIT trap; A's HTTP library preserves these caller traps.
source "$(dirname -- "${BASH_SOURCE[0]}")/github-identity.sh"
source "$(dirname -- "${BASH_SOURCE[0]}")/mcp.sh"

_GITHUB_SCRATCH=''

github_connect() {
    [[ -n "${GITHUB_MCP_URL:-}" && -n "${GITHUB_TOKEN:-}" ]] || {
        github_error 'GITHUB_MCP_URL and GITHUB_TOKEN are required'; return 1;
    }
    umask 077
    _GITHUB_SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/lean-sdd-github.XXXXXXXX") || return 1
    trap 'rm -rf -- "$_GITHUB_SCRATCH"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    mcp_connect "$GITHUB_MCP_URL" "$GITHUB_TOKEN" > "$_GITHUB_SCRATCH/initialize.json"
}

# Decode exactly one value of the requested object/array type (object default).
# Conflicting structured/text output is ambiguous; C consumes PR/review arrays.
github_call() {
    local result_type="${3:-object}"
    [[ "$result_type" == object || "$result_type" == array ]] || return 2
    mcp_call "$1" "$2" > "$_GITHUB_SCRATCH/result.json" || return 1
    if ! jq -e --arg expected_type "$result_type" '
        def text_object:
            if (.content | length) != 1 or .content[0].type != "text" then error("content")
            else .content[0].text | fromjson | if type == $expected_type then . else error("type") end end;
        if has("structuredContent") then
            .structuredContent as $data |
            if ($data | type) != $expected_type then error("type")
            elif (.content | length) == 0 then $data
            elif text_object == $data then $data else error("conflict") end
        else text_object end
    ' "$_GITHUB_SCRATCH/result.json" > "$_GITHUB_SCRATCH/data.json" 2>/dev/null; then
        github_error 'malformed or ambiguous tool data'
        return 1
    fi
}

# Full issue_read shape, verified through MCP. A missing/null body is not an
# empty body: callers must not invent an authoritative specification.
github_normalize_issue() {
    local owner="$1" repo="$2" number="$3"
    if ! jq -ce --arg owner "$owner" --arg repo "$repo" --argjson number "$number" '
        select(.number == $number and (.number | type == "number" and floor == . and . > 0)) |
        select(.html_url | type == "string") |
        select((.html_url | ascii_downcase) == ("https://github.com/" + $owner + "/" + $repo + "/issues/" + ($number|tostring) | ascii_downcase)) |
        select((has("pull_request")|not) and ((has("__typename")|not) or .__typename == "Issue")) |
        select((.title | type == "string" and test("\\S")) and (.body | type == "string")) |
        select(.state == "open" or .state == "closed") |
        select((has("repository_url")|not) or
            (.repository_url | ascii_downcase) == ("https://api.github.com/repos/" + $owner + "/" + $repo | ascii_downcase)) |
        select((has("updated_at")|not) or (.updated_at | type == "string" and length > 0)) |
        {owner:$owner,repo:$repo,issue_number:.number,issue_url:.html_url,title,body,state,
         issue_reference:($owner + "/" + $repo + "#" + ($number|tostring)),BRANCH:("gh-" + ($number|tostring))}
    ' "$_GITHUB_SCRATCH/data.json" > "$_GITHUB_SCRATCH/issue.json" 2>/dev/null; then
        github_error 'issue identity, entity type, specification or state is invalid'
        return 1
    fi
    # Preserve optional observed modification metadata; never infer a timestamp.
    jq --slurpfile raw "$_GITHUB_SCRATCH/data.json" '
        if $raw[0] | has("updated_at") then . + {updated_at:$raw[0].updated_at} else . end
    ' "$_GITHUB_SCRATCH/issue.json"
}

github_read_issue() {
    local arguments=''
    arguments=$(jq -cn --arg owner "$1" --arg repo "$2" --argjson number "$3" \
        '{owner:$owner,repo:$repo,issue_number:$number,method:"get"}') || return 1
    github_call issue_read "$arguments" || return 1
    github_normalize_issue "$1" "$2" "$3"
}

# Write results currently return id (database ID as text) and url, not an issue
# number. Extract the number only from a returned, repository-validated issue URL.
github_write_identity() {
    local owner="$1" repo="$2" expected="${3:-}"
    if ! jq -ce --arg owner "$owner" --arg repo "$repo" --arg expected "$expected" '
        select((.id | type == "string" and test("^[1-9][0-9]*$")) and (.url | type == "string")) |
        select((has("pull_request")|not) and ((has("__typename")|not) or .__typename == "Issue")) |
        . as $raw | .url | capture("^https://github.com/(?<owner>[A-Za-z0-9-]+)/(?<repo>[A-Za-z0-9_.-]+)/issues/(?<number>[1-9][0-9]{0,14})$") |
        select((.owner|ascii_downcase) == ($owner|ascii_downcase) and (.repo|ascii_downcase) == ($repo|ascii_downcase)) |
        select($expected == "" or .number == $expected) |
        select(($raw|has("number")|not) or $raw.number == (.number|tonumber)) |
        {owner:$owner,repo:$repo,issue_number:(.number|tonumber),issue_url:$raw.url,issue_id:$raw.id}
    ' "$_GITHUB_SCRATCH/data.json" 2>/dev/null; then
        github_error 'write returned no reliable issue identity; outcome unconfirmed; do not retry'
        return 1
    fi
}
