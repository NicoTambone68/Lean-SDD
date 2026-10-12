#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-pr.sh"
c_phase=publication
trap c_failed ERR
c_input "$@"
jq '.title + "\n" + .body' <<< "$C_INPUT" | c_nonclosing
# A non-closing reference is required in the reviewable body as well as commit.
jq .body <<< "$C_INPUT" | c_reference
c_stage=local_preflight
c_local
c_stage=mcp_preflight
c_connect
c_stage=existing_pr_check
c_no_existing_pr
# Recheck local state after network reads, then push this SHA explicitly so a
# concurrent local branch movement cannot silently publish a different commit.
c_stage=before_push
c_local
c_stage=push
c_push=unconfirmed
git -c push.followTags=false push origin "$SOURCE_COMMIT:refs/heads/$BRANCH" > "$_GITHUB_SCRATCH/git.log" 2>&1
c_push=confirmed
c_stage=after_push
c_local
c_stage=create_pr
c_create=unconfirmed
arguments=$(jq -c '{owner,repo,title,body,head:.BRANCH,base:.WORKING_BRANCH}' <<< "$C_INPUT")
github_call create_pull_request "$arguments"
# GitHub's create result is MinimalResponse {id,url}. Derive the PR number
# solely from the returned validated URL, never from a guessed issue number.
PR_ID=$(jq -er --arg repository "$OWNER/$REPO" '
    select(.id|type == "string" and test("^[1-9][0-9]*$")) |
    . as $raw | .url | capture("^https://github.com/(?<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?<number>[1-9][0-9]{0,14})$") |
    select((.repo|ascii_downcase) == ($repository|ascii_downcase)) |
    select(($raw|has("number")|not) or $raw.number == (.number|tonumber)) | .number
' "$_GITHUB_SCRATCH/data.json" 2>/dev/null)
c_create=identified
cp "$_GITHUB_SCRATCH/data.json" "$_GITHUB_SCRATCH/created.json"
c_stage=verify_created_pr
c_pr_read
c_pr_validate open
c_local
# SOURCE_COMMIT comes from the validated PR head, which must equal the input.
jq -cn --argjson input "$C_INPUT" --slurpfile pr "$_GITHUB_SCRATCH/data.json" \
    '$input | {owner,repo,issue_number,issue_url,BRANCH,WORKING_BRANCH,
      issue_reference:(.owner + "/" + .repo + "#" + (.issue_number|tostring)),
      PR_ID:$pr[0].number,PR_URL:$pr[0].html_url,SOURCE_COMMIT:$pr[0].head.sha}'
