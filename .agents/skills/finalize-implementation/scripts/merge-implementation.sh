#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-pr.sh"
c_phase=merge
trap c_failed ERR
c_input "$@"
c_stage=local_preflight
c_local
c_stage=mcp_preflight
c_connect
c_stage=pr_preflight
c_pr_read
c_pr_validate open
c_ready
c_stage=reviews_and_checks
c_diagnostics
c_stage=immediate_revalidation
c_local
c_pr_read
c_pr_validate open
c_ready
BASE_BEFORE=$(jq -r .base.sha "$_GITHUB_SCRATCH/data.json")
c_stage=merge_request
c_merge=unconfirmed
arguments=$(jq -c '{owner,repo,pullNumber:.PR_ID,expectedHeadSha:.SOURCE_COMMIT,merge_method:"merge"}' <<< "$C_INPUT")
github_call merge_pull_request "$arguments"
MERGE_COMMIT=$(jq -er 'select(.merged == true) | .sha | select(type == "string" and test("^[0-9a-f]{40}$"))' "$_GITHUB_SCRATCH/data.json")
c_merge=reported
c_stage=verify_remote_merge
c_pr_read
c_pr_validate merged
# If an endpoint later exposes this field, require agreement as well. Current
# MCP minimal PR responses omit it; an independent commit read follows.
jq -e --arg merge "$MERGE_COMMIT" '(has("merge_commit_sha")|not) or .merge_commit_sha == $merge' "$_GITHUB_SCRATCH/data.json" >/dev/null
cp "$_GITHUB_SCRATCH/data.json" "$_GITHUB_SCRATCH/merged-pr.json"
arguments=$(jq -cn --arg owner "$OWNER" --arg repo "$REPO" --arg sha "$MERGE_COMMIT" '{owner:$owner,repo:$repo,sha:$sha}')
github_call get_commit "$arguments"
jq -e --arg sha "$MERGE_COMMIT" --arg repository "$OWNER/$REPO" \
    '.sha == $sha and (.html_url|ascii_downcase) == ("https://github.com/" + $repository + "/commit/" + $sha|ascii_downcase)' \
    "$_GITHUB_SCRATCH/data.json" >/dev/null
c_verified=true
c_merge=verified
c_stage=before_local_sync
c_local
# Fetch the explicit base to its tracking ref. No '+' refspec, force, reset,
# inferred upstream, or detached checkout. Verify actual merge parents before
# touching the local working branch, using objects from the verified remote.
c_stage=fetch
git fetch --no-tags origin "refs/heads/$WORKING_BRANCH:refs/remotes/origin/$WORKING_BRANCH" > "$_GITHUB_SCRATCH/git.log" 2>&1
REMOTE_COMMIT=$(git rev-parse "refs/remotes/origin/$WORKING_BRANCH")
c_stage=merge_ancestry
git merge-base --is-ancestor "$MERGE_COMMIT" "$REMOTE_COMMIT" >/dev/null 2>&1
[[ "$(git rev-list --parents -n 1 "$MERGE_COMMIT" | awk '{print NF}')" == 3 ]]
[[ "$(git rev-parse "$MERGE_COMMIT^2")" == "$SOURCE_COMMIT" ]]
git merge-base --is-ancestor "$BASE_BEFORE" "$MERGE_COMMIT^1" >/dev/null 2>&1
c_stage=switch_working_branch
git switch "$WORKING_BRANCH" > "$_GITHUB_SCRATCH/git.log" 2>&1
c_stage=fast_forward
git merge --ff-only "refs/remotes/origin/$WORKING_BRANCH" > "$_GITHUB_SCRATCH/git.log" 2>&1
c_stage=verify_local_sync
[[ "$(git branch --show-current)" == "$WORKING_BRANCH" ]]
[[ -z "$(git status --porcelain --untracked-files=all)" ]]
LOCAL_COMMIT=$(git rev-parse HEAD)
[[ "$LOCAL_COMMIT" == "$REMOTE_COMMIT" && "$LOCAL_COMMIT" == "$(git rev-parse "refs/remotes/origin/$WORKING_BRANCH")" ]]
git merge-base --is-ancestor "$MERGE_COMMIT" HEAD >/dev/null 2>&1
jq -cn --argjson retained "$C_INPUT" --arg merge "$MERGE_COMMIT" --arg local "$LOCAL_COMMIT" --arg remote "$REMOTE_COMMIT" \
    '$retained + {merged:true,merge_commit:$merge,local_branch:$retained.WORKING_BRANCH,
      local_commit:$local,remote_commit:$remote,synchronized:true,clean:true}'
