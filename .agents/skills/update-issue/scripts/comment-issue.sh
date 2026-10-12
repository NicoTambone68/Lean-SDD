#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-issues.sh"
[[ $# == 4 ]] || { github_error 'usage: comment-issue.sh <owner> <repo> <issue-number> <text>'; exit 2; }
github_issue_input "$1" "$2" "$3"
github_text_input "$4"
arguments=$(jq -cn --arg owner "$1" --arg repo "$2" --argjson number "$3" --arg body "$4" \
    '{owner:$owner,repo:$repo,issue_number:$number,body:$body}')
github_connect
# Reject PRs and identity mismatches before submitting an issue audit comment.
github_read_issue "$1" "$2" "$3" > "$_GITHUB_SCRATCH/target.json"
if ! github_call add_issue_comment "$arguments"; then
    github_error "comment on $1/$2#$3 is unconfirmed; no retry or recursive audit"
    exit 1
fi
if ! jq -ce --arg owner "$1" --arg repo "$2" --argjson number "$3" '
    select(.id | type == "string" and test("^[1-9][0-9]*$")) |
    select(.url | type == "string") |
    select((.url | ascii_downcase) == ("https://github.com/" + $owner + "/" + $repo + "/issues/" + ($number|tostring) + "#issuecomment-" + .id | ascii_downcase)) |
    {owner:$owner,repo:$repo,issue_number:$number,comment_id:.id,comment_url:.url}
' "$_GITHUB_SCRATCH/data.json" 2>/dev/null; then
    github_error "comment on $1/$2#$3 returned no reliable identifier; outcome unconfirmed; no further audit"
    exit 1
fi
