#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-issues.sh"
[[ $# == 1 ]] || { github_error 'usage: list-repositories.sh <explicit-search-query>'; exit 2; }
github_text_input "$1"
github_connect
github_call get_me '{}'
printf '[]\n' > "$_GITHUB_SCRATCH/repositories.json"
printf '[]\n' > "$_GITHUB_SCRATCH/reasons.json"
reason() {
    jq --arg reason "$1" '. + [$reason] | unique' "$_GITHUB_SCRATCH/reasons.json" > "$_GITHUB_SCRATCH/next.json"
    mv -- "$_GITHUB_SCRATCH/next.json" "$_GITHUB_SCRATCH/reasons.json"
}
total=''
for ((page=1; page<=10; page++)); do
    arguments=$(jq -cn --arg query "$1" --argjson page "$page" \
        '{query:$query,page:$page,perPage:100,minimal_output:false}')
    github_call search_repositories "$arguments"
    # Validate every record rather than silently dropping malformed entries.
    if ! jq -e '
        def slug: type == "string" and test("^[A-Za-z0-9][A-Za-z0-9-]{0,38}$") and
            (endswith("-")|not) and (contains("--")|not);
        def name: type == "string" and test("^[A-Za-z0-9_.-]{1,100}$") and . != "." and . != "..";
        select((.total_count | type == "number" and floor == . and . >= 0 and . <= 9007199254740991) and
               (.incomplete_results | type == "boolean") and (.items | type == "array" and length <= 100)) |
        .items |= map(
            if (.owner.login | slug) and (.name | name) and (.html_url | type == "string") and
               ((.html_url|ascii_downcase) == ("https://github.com/" + .owner.login + "/" + .name | ascii_downcase)) and
               ((has("full_name")|not) or (.full_name == (.owner.login + "/" + .name))) and
               ((has("visibility")|not) or (.visibility == "public" or .visibility == "private" or .visibility == "internal")) and
               ((has("archived")|not) or (.archived|type == "boolean")) and
               ((has("private")|not) or (.private|type == "boolean"))
            then {owner:.owner.login,name,url:.html_url} +
                (if has("visibility") then {visibility} else {} end) +
                (if has("archived") then {archived} else {} end) +
                (if has("private") then {private} else {} end)
            else error("repository") end)
    ' "$_GITHUB_SCRATCH/data.json" > "$_GITHUB_SCRATCH/page.json" 2>/dev/null; then
        github_error 'invalid repository search response'; exit 1
    fi
    current_total=$(jq -r '.total_count' "$_GITHUB_SCRATCH/page.json")
    if [[ -n "$total" && "$total" != "$current_total" ]]; then reason total_changed; fi
    total="$current_total"
    if jq -e '.incomplete_results' "$_GITHUB_SCRATCH/page.json" >/dev/null; then reason server_incomplete; fi
    before=$(jq length "$_GITHUB_SCRATCH/repositories.json")
    count=$(jq '.items|length' "$_GITHUB_SCRATCH/page.json")
    jq --slurpfile next "$_GITHUB_SCRATCH/page.json" \
        '. + $next[0].items | unique_by((.owner + "/" + .name)|ascii_downcase)' \
        "$_GITHUB_SCRATCH/repositories.json" > "$_GITHUB_SCRATCH/next.json"
    mv -- "$_GITHUB_SCRATCH/next.json" "$_GITHUB_SCRATCH/repositories.json"
    after=$(jq length "$_GITHUB_SCRATCH/repositories.json")
    if ((after != before + count)); then reason repeated_results; break; fi
    if ((after >= total)); then
        if ((after > total)); then reason inconsistent_total; fi
        break
    fi
    if ((count < 100)); then reason premature_end; break; fi
    if ((page == 10)); then reason search_limit; break; fi
done
jq -cn --arg query "$1" --argjson total "$total" --argjson pages "$page" \
    --slurpfile repositories "$_GITHUB_SCRATCH/repositories.json" --slurpfile reasons "$_GITHUB_SCRATCH/reasons.json" \
    '{query:$query,repositories:$repositories[0],total_count:$total,pages:$pages,
      incomplete_results:($reasons[0]|length > 0),incomplete_reasons:$reasons[0]}'
