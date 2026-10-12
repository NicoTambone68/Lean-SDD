#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-issues.sh"
[[ $# == 3 ]] || { github_error 'usage: close-issue.sh <owner> <repo> <issue-number>'; exit 2; }
github_issue_input "$1" "$2" "$3"
arguments=$(jq -cn --arg owner "$1" --arg repo "$2" --argjson number "$3" \
    '{owner:$owner,repo:$repo,issue_number:$number,method:"update",state:"closed",state_reason:"completed"}')
github_connect
github_read_issue "$1" "$2" "$3" > "$_GITHUB_SCRATCH/before.json"
if ! github_call issue_write "$arguments" ||
   ! github_write_identity "$1" "$2" "$3" > "$_GITHUB_SCRATCH/updated.json" ||
   ! github_read_issue "$1" "$2" "$3" > "$_GITHUB_SCRATCH/after.json"; then
    github_error "closure of $1/$2#$3 could not be confirmed; no further audit or retry"
    exit 1
fi
if ! jq -e '.state == "closed"' "$_GITHUB_SCRATCH/after.json" >/dev/null; then
    github_error "closure of $1/$2#$3 failed: targeted read observed state=open"
    exit 1
fi
jq -c '{owner,repo,issue_number,issue_url,state}' "$_GITHUB_SCRATCH/after.json"
