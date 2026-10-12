#!/usr/bin/env bash
# Shared deterministic operations for publication and merge. No approval policy.
source "$(dirname -- "${BASH_SOURCE[0]}")/github-issues.sh"

c_phase=''
c_stage=input
c_push=not_attempted
c_create=not_attempted
c_merge=not_attempted
c_verified=false
PR_ID=''

c_failed() {
    trap - ERR
    printf 'ERROR: GitHub %s stopped during %s; push=%s create=%s PR_ID=%s merge=%s remote_verified=%s; no automatic retry or dependent actions\n' \
        "$c_phase" "$c_stage" "$c_push" "$c_create" "${PR_ID:-unknown}" "$c_merge" "$c_verified" >&2
    if [[ "$c_stage" != input ]]; then
        printf 'Local state: branch=%s HEAD=%s; existing changes and remote effects are preserved\n' \
            "$(git branch --show-current 2>/dev/null || true)" "$(git rev-parse --verify HEAD 2>/dev/null || true)" >&2
    fi
    exit 1
}

c_die() { github_error "$1"; }

c_input() {
    [[ $# == 1 && -f "$1" && -r "$1" ]] || { c_die 'one readable JSON input file is required'; return 1; }
    # Validate type/presence before extracting shell values. Reject NUL, duplicate
    # JSON documents and additional fields, rather than silently altering data.
    C_INPUT=$(jq -ces --arg phase "$c_phase" '
        def string: type == "string" and (contains("\u0000")|not);
        def positive: type == "number" and floor == . and . > 0 and . < 1e15;
        select(length == 1) | .[0] | select(type == "object") |
        ["owner","repo","issue_number","issue_url","BRANCH","WORKING_BRANCH","SOURCE_COMMIT"] as $common |
        (if $phase == "publication" then $common + ["title","body"]
         else $common + ["issue_reference","PR_ID","PR_URL"] end | sort) as $keys |
        select((keys|sort) == $keys) |
        select(all(to_entries[]; if .key == "issue_number" or .key == "PR_ID" then .value|positive else .value|string end)) |
        select(all(to_entries[]; if .key == "title" or .key == "body" or (.value|type) != "string" then true else .value|test("[\u0000-\u001f\u007f]")|not end)) |
        select(.SOURCE_COMMIT|test("^[0-9a-f]{40}$")) |
        select(.BRANCH == ("gh-" + (.issue_number|tostring))) |
        select(.WORKING_BRANCH != .BRANCH) |
        select((.issue_url|ascii_downcase) == ("https://github.com/" + .owner + "/" + .repo + "/issues/" + (.issue_number|tostring)|ascii_downcase)) |
        if $phase == "merge" then
            select(.issue_reference == (.owner + "/" + .repo + "#" + (.issue_number|tostring))) |
            select((.PR_URL|ascii_downcase) == ("https://github.com/" + .owner + "/" + .repo + "/pull/" + (.PR_ID|tostring)|ascii_downcase))
        else select((.title|test("\\S")) and (.body|test("\\S"))) end
    ' "$1" 2>/dev/null) || { c_die 'invalid or incomplete phase input; retain the exact publication tuple'; return 1; }
    OWNER=$(jq -r .owner <<< "$C_INPUT")
    REPO=$(jq -r .repo <<< "$C_INPUT")
    ISSUE_NUMBER=$(jq -r .issue_number <<< "$C_INPUT")
    github_issue_input "$OWNER" "$REPO" "$ISSUE_NUMBER" || return 1
    BRANCH=$(jq -r .BRANCH <<< "$C_INPUT")
    WORKING_BRANCH=$(jq -r .WORKING_BRANCH <<< "$C_INPUT")
    SOURCE_COMMIT=$(jq -r .SOURCE_COMMIT <<< "$C_INPUT")
    ISSUE_REFERENCE="$OWNER/$REPO#$ISSUE_NUMBER"
    [[ -n "$WORKING_BRANCH" && "$WORKING_BRANCH" != -* && "$WORKING_BRANCH" != HEAD &&
       "$WORKING_BRANCH" != @ && "$WORKING_BRANCH" != refs/* && "$WORKING_BRANCH" != *'@{'* ]] || {
        c_die 'explicit literal working branch is required'; return 1;
    }
    command -v git >/dev/null || return 1
    git check-ref-format --branch "$WORKING_BRANCH" >/dev/null 2>&1 || { c_die 'invalid working branch'; return 1; }
    if [[ "$c_phase" == merge ]]; then PR_ID=$(jq -r .PR_ID <<< "$C_INPUT"); fi
}

c_nonclosing() {
    # Conservative detection also catches Markdown links/formatting and colon
    # forms. False positives must be reworded, never silently stripped.
    jq -e 'test("(?i)(?<![A-Za-z0-9])(close[sd]?|fix(e[sd])?|resolve[sd]?)(?![A-Za-z0-9])\\s*[^\\r\\n]*(#[0-9]+|https?://github\\.com/[^ /]+/[^ /]+/issues/)")|not' >/dev/null || {
        c_die 'automatic issue-closing reference is not permitted'; return 1;
    }
}

c_reference() {
    jq -e --arg reference "$ISSUE_REFERENCE" '
        test("(^|[^A-Za-z0-9_./-])" + ($reference|gsub("\\.";"\\.")) + "($|[^0-9])")
    ' >/dev/null || { c_die 'canonical non-closing issue reference is required'; return 1; }
}

c_remote() {
    local fetch='' push='' identity='' url='' expected="$OWNER/$REPO"
    fetch=$(git remote get-url --all origin 2>/dev/null) || { c_die 'origin fetch destination unavailable'; return 1; }
    push=$(git remote get-url --push --all origin 2>/dev/null) || { c_die 'origin push destination unavailable'; return 1; }
    for url in "$fetch" "$push"; do
        [[ "$url" != *$'\n'* ]] || { c_die 'multiple origin destinations are not permitted'; return 1; }
        identity=$(github_remote_identity "$url") || { c_die 'unsupported effective GitHub origin destination'; return 1; }
        [[ "$identity" == "${expected,,}" ]] || { c_die 'origin repository differs from retained identity'; return 1; }
    done
}

c_local() {
    [[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" == true ]] || { c_die 'not in a Git worktree'; return 1; }
    [[ "$(git branch --show-current)" == "$BRANCH" ]] || { c_die 'wrong branch or detached HEAD'; return 1; }
    [[ "$(git rev-parse HEAD)" == "$SOURCE_COMMIT" ]] || { c_die 'HEAD differs from approved source commit'; return 1; }
    [[ -w "$(git rev-parse --git-dir)" && -w "$(git rev-parse --git-common-dir)" ]] || { c_die 'Git metadata is not writable'; return 1; }
    [[ -z "$(git status --porcelain --untracked-files=all)" ]] || { c_die 'index or worktree is dirty'; return 1; }
    git show-ref --verify --quiet "refs/heads/$WORKING_BRANCH" || { c_die 'retained working branch is missing locally'; return 1; }
    c_remote || return 1
    local message=''
    message=$(git log -1 --format=%B) || return 1
    jq -n --arg text "$message" '$text' | c_reference || return 1
    jq -n --arg text "$message" '$text' | c_nonclosing
}

c_connect() {
    github_connect || return 1
    mcp_list_tools > "$_GITHUB_SCRATCH/tools.json" || return 1
    c_capabilities "$_GITHUB_SCRATCH/tools.json" || return 1
    github_call get_me '{}' || return 1
    jq -e '.login|type == "string" and test("^[A-Za-z0-9][A-Za-z0-9-]*$")' "$_GITHUB_SCRATCH/data.json" >/dev/null || {
        c_die 'MCP identity read failed validation; write access is not established'; return 1;
    }
}

# Read-only deployment check, also used on every phase invocation.
c_capabilities() {
    [[ $# == 1 && -r "$1" && ( "$c_phase" == publication || "$c_phase" == merge ) ]] || {
        c_die "capability check requires a tools file and explicit publication/merge phase"; return 1;
    }
    # Revalidate the deployed phase-specific contract after every approval pause.
    jq -e --arg phase "$c_phase" '
        .tools as $tools |
        def schema($name): [$tools[]|select(.name == $name)] | select(length == 1) | .[0].inputSchema;
        def fields($name;$fields): schema($name) as $s | $s.type == "object" and
            all($fields|to_entries[]; . as $f | $s.properties[$f.key].type == $f.value);
        fields("get_me";{}) and
        fields("pull_request_read";{owner:"string",repo:"string",pullNumber:"number",method:"string",page:"number",perPage:"number"}) and
        ((schema("pull_request_read").properties.method.enum|index("get")) != null) and
        if $phase == "publication" then
            fields("list_pull_requests";{owner:"string",repo:"string",head:"string",base:"string",state:"string",page:"number",perPage:"number"}) and
            fields("create_pull_request";{owner:"string",repo:"string",head:"string",base:"string",title:"string",body:"string"})
        else
            fields("merge_pull_request";{owner:"string",repo:"string",pullNumber:"number",expectedHeadSha:"string",merge_method:"string"}) and
            ((schema("merge_pull_request").properties.merge_method.enum|index("merge")) != null) and
            fields("get_commit";{owner:"string",repo:"string",sha:"string"}) and
            all(["get_status","get_reviews","get_check_runs"][]; . as $method |
                (schema("pull_request_read").properties.method.enum|index($method)) != null)
        end
    ' "$1" >/dev/null || { c_die 'required MCP phase capability missing (merge requires expectedHeadSha and commit verification)'; return 1; }
}

c_pr_read() {
    local method="${1:-get}" page="${2:-1}" kind="${3:-object}" args=''
    args=$(jq -cn --arg owner "$OWNER" --arg repo "$REPO" --argjson pr "$PR_ID" --arg method "$method" --argjson page "$page" \
        '{owner:$owner,repo:$repo,pullNumber:$pr,method:$method,page:$page,perPage:100}') || return 1
    github_call pull_request_read "$args" "$kind"
}

c_pr_validate() {
    local state="$1"
    jq -e --arg owner "$OWNER" --arg repo "$REPO" --arg branch "$BRANCH" --arg base "$WORKING_BRANCH" \
        --arg sha "$SOURCE_COMMIT" --argjson pr "$PR_ID" --arg state "$state" '
        .number == $pr and
        (.html_url|type == "string") and
        ((.html_url|ascii_downcase) == ("https://github.com/" + $owner + "/" + $repo + "/pull/" + ($pr|tostring)|ascii_downcase)) and
        (.head.repo.full_name|ascii_downcase) == ($owner + "/" + $repo|ascii_downcase) and
        (.base.repo.full_name|ascii_downcase) == ($owner + "/" + $repo|ascii_downcase) and
        .head.ref == $branch and .base.ref == $base and .head.sha == $sha and
        (.base.sha|type == "string" and test("^[0-9a-f]{40}$")) and
        if $state == "open" then .state == "open" and .merged == false and .draft == false
        else .state == "closed" and .merged == true and (.merged_at|type == "string" and length > 0) end
    ' "$_GITHUB_SCRATCH/data.json" >/dev/null 2>&1 || { c_die 'PR repository, refs, source SHA or state differs from retained identity'; return 1; }
}

c_no_existing_pr() {
    local page='' args='' count='' known=''
    printf '[]\n' > "$_GITHUB_SCRATCH/seen.json"
    for ((page=1; page<=100; page++)); do
        args=$(jq -cn --arg owner "$OWNER" --arg repo "$REPO" --arg head "$OWNER:$BRANCH" --arg base "$WORKING_BRANCH" --argjson page "$page" \
            '{owner:$owner,repo:$repo,head:$head,base:$base,state:"open",page:$page,perPage:100}') || return 1
        github_call list_pull_requests "$args" array || return 1
        jq -e --arg repository "$OWNER/$REPO" '
            length <= 100 and all(.[]; (.number|type == "number" and floor == . and . > 0 and . < 1e15) and
                .state == "open" and (.head.ref|type == "string") and (.head.repo.full_name|type == "string") and
                (.base.ref|type == "string") and (.base.repo.full_name|ascii_downcase) == ($repository|ascii_downcase) and
                (.html_url|ascii_downcase) == ("https://github.com/" + $repository + "/pull/" + (.number|tostring)|ascii_downcase))
        ' "$_GITHUB_SCRATCH/data.json" >/dev/null 2>&1 || { c_die 'malformed existing PR page'; return 1; }
        known=$(jq -c --arg repository "$OWNER/$REPO" --arg head "$BRANCH" --arg base "$WORKING_BRANCH" \
            '[.[]|select((.head.repo.full_name|ascii_downcase) == ($repository|ascii_downcase) and .head.ref == $head and .base.ref == $base)|{number,html_url,head,base}]' \
            "$_GITHUB_SCRATCH/data.json") || return 1
        if [[ "$known" != '[]' ]]; then
            # Fields above are validated; emit only safe retained facts.
            jq -c '[.[]|{PR_ID:.number,PR_URL:.html_url}]' <<< "$known" >&2
            c_die 'matching open PR exists; explicit recovery decision required; nothing pushed or created'; return 1
        fi
        count=$(jq length "$_GITHUB_SCRATCH/data.json") || return 1
        jq -e --slurpfile next "$_GITHUB_SCRATCH/data.json" \
            '. + [$next[0][].number] | if length == (unique|length) then . else error("repeated page") end' \
            "$_GITHUB_SCRATCH/seen.json" > "$_GITHUB_SCRATCH/next.json" || { c_die 'repeated existing PR results'; return 1; }
        mv "$_GITHUB_SCRATCH/next.json" "$_GITHUB_SCRATCH/seen.json" || return 1
        if ((count < 100)); then return 0; fi
    done
    c_die 'existing PR pagination boundary reached; completeness unconfirmed'
}

c_ready() {
    jq -e '.mergeable_state == "clean"' "$_GITHUB_SCRATCH/data.json" >/dev/null || {
        c_die 'mergeability is blocked, pending or unknown; merge-commit eligibility unconfirmed'; return 1;
    }
}

c_diagnostics() {
    local page='' count='' total='' previous='' args=''
    c_pr_read get_status || return 1
    jq -e --arg sha "$SOURCE_COMMIT" '
        .sha == $sha and (.total_count|type == "number" and floor == . and . >= 0) and
        (.statuses|type == "array") and .total_count == (.statuses|length) and
        if .total_count == 0 then .state == "pending" or .state == "success"
        else .state == "success" and all(.statuses[]; .state == "success") end
    ' "$_GITHUB_SCRATCH/data.json" >/dev/null || { c_die 'commit statuses failed, pending, incomplete or for a different SHA'; return 1; }
    cp "$_GITHUB_SCRATCH/data.json" "$_GITHUB_SCRATCH/statuses.json" || return 1
    printf '[]\n' > "$_GITHUB_SCRATCH/checks.json"
    for ((page=1; page<=100; page++)); do
        c_pr_read get_check_runs "$page" || return 1
        jq -e '.total_count|type == "number" and floor == . and . >= 0' "$_GITHUB_SCRATCH/data.json" >/dev/null || return 1
        total=$(jq .total_count "$_GITHUB_SCRATCH/data.json") || return 1
        [[ -z "$previous" || "$total" == "$previous" ]] || { c_die 'check count changed during pagination'; return 1; }
        previous="$total"
        jq -e '(.check_runs|type == "array" and length <= 100) and all(.check_runs[];
            (.id|type == "number" and floor == . and . > 0) and .status == "completed" and
            (.conclusion == "success" or .conclusion == "neutral" or .conclusion == "skipped"))' \
            "$_GITHUB_SCRATCH/data.json" >/dev/null || { c_die 'check runs failed, pending, unknown or malformed'; return 1; }
        count=$(jq '.check_runs|length' "$_GITHUB_SCRATCH/data.json") || return 1
        jq -e --slurpfile next "$_GITHUB_SCRATCH/data.json" '. + $next[0].check_runs |
            if length == (unique_by(.id)|length) then . else error("repeated check") end' \
            "$_GITHUB_SCRATCH/checks.json" > "$_GITHUB_SCRATCH/next.json" || return 1
        mv "$_GITHUB_SCRATCH/next.json" "$_GITHUB_SCRATCH/checks.json" || return 1
        if ((count < 100)); then break; fi
    done
    [[ "$(jq length "$_GITHUB_SCRATCH/checks.json")" == "$total" && "$page" -le 100 ]] || { c_die 'incomplete check run enumeration'; return 1; }
    printf '[]\n' > "$_GITHUB_SCRATCH/reviews.json"
    for ((page=1; page<=100; page++)); do
        c_pr_read get_reviews "$page" array || return 1
        jq -e 'length <= 100 and all(.[]; (.id|type == "number" and floor == . and . > 0) and
            (.user.login|type == "string" and length > 0) and
            (.state == "APPROVED" or .state == "CHANGES_REQUESTED" or .state == "DISMISSED" or .state == "COMMENTED"))' \
            "$_GITHUB_SCRATCH/data.json" >/dev/null || { c_die 'reviews pending, unknown or malformed'; return 1; }
        count=$(jq length "$_GITHUB_SCRATCH/data.json") || return 1
        jq -e --slurpfile next "$_GITHUB_SCRATCH/data.json" '. + $next[0] |
            if length == (unique_by(.id)|length) then . else error("repeated review") end' \
            "$_GITHUB_SCRATCH/reviews.json" > "$_GITHUB_SCRATCH/next.json" || return 1
        mv "$_GITHUB_SCRATCH/next.json" "$_GITHUB_SCRATCH/reviews.json" || return 1
        if ((count < 100)); then break; fi
    done
    [[ "$page" -le 100 ]] || { c_die 'review pagination incomplete'; return 1; }
    jq -e '[.[]|select(.state != "COMMENTED")]|group_by(.user.login|ascii_downcase)|
        all(.[]; (sort_by(.id)|last|.state) != "CHANGES_REQUESTED")' "$_GITHUB_SCRATCH/reviews.json" >/dev/null || {
        c_die 'latest review requests changes'; return 1;
    }
}
