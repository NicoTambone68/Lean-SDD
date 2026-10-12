#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-issues.sh"
[[ $# == 4 ]] || { github_error 'usage: create-issue.sh <owner> <repo> <title> <body>'; exit 2; }
github_repository_input "$1" "$2"
github_text_input "$3"
github_text_input "$4"
arguments=$(jq -cn --arg owner "$1" --arg repo "$2" --arg title "$3" --arg body "$4" \
    '{owner:$owner,repo:$repo,method:"create",title:$title,body:$body}')
github_connect
if ! github_call issue_write "$arguments"; then
    github_error "creation in $1/$2 is unconfirmed; no second create will be attempted"
    exit 1
fi
github_write_identity "$1" "$2" > "$_GITHUB_SCRATCH/created.json"
number=$(jq -r '.issue_number' "$_GITHUB_SCRATCH/created.json")
if ! github_read_issue "$1" "$2" "$number" > "$_GITHUB_SCRATCH/created-issue.json"; then
    github_error "created issue $1/$2#$number could not be confirmed; do not retry creation"
    exit 1
fi
jq -c --slurpfile created "$_GITHUB_SCRATCH/created.json" '. + {issue_id:$created[0].issue_id}' "$_GITHUB_SCRATCH/created-issue.json"
