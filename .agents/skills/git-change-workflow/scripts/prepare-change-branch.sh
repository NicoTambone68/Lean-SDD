#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-identity.sh"
[[ $# == 4 ]] || { github_error 'usage: prepare-change-branch.sh <owner> <repo> <issue-number> <working-branch>'; exit 2; }
github_issue_input "$1" "$2" "$3"
WORKING_BRANCH="$4"
BRANCH="gh-$3"
# Validate literal names before reading repository state or mutating Git.
[[ -n "$WORKING_BRANCH" && "$WORKING_BRANCH" != -* && "$WORKING_BRANCH" != HEAD &&
   "$WORKING_BRANCH" != @ && "$WORKING_BRANCH" != refs/* && "$WORKING_BRANCH" != *'@{'* ]] || {
    github_error 'explicit literal working branch is required'; exit 1;
}
command -v git >/dev/null && command -v jq >/dev/null || { github_error 'git and jq are required'; exit 1; }
git check-ref-format --branch "$WORKING_BRANCH" >/dev/null 2>&1 || {
    github_error 'invalid working branch'; exit 1;
}
[[ "$WORKING_BRANCH" != "$BRANCH" ]] || { github_error 'working branch must differ from issue branch'; exit 1; }
[[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" == true ]] || {
    github_error 'not inside a Git worktree'; exit 1;
}
git symbolic-ref -q HEAD >/dev/null 2>&1 || { github_error 'detached HEAD is not supported'; exit 1; }
git_dir=$(git rev-parse --git-dir)
common_dir=$(git rev-parse --git-common-dir)
[[ -w "$git_dir" && -w "$common_dir" ]] || { github_error 'Git metadata is not writable'; exit 1; }
status=$(git status --porcelain --untracked-files=all) || { github_error 'cannot inspect worktree'; exit 1; }
[[ -z "$status" ]] || { github_error 'working tree is not clean'; exit 1; }
git show-ref --verify --quiet "refs/heads/$WORKING_BRANCH" || { github_error 'working branch does not exist locally'; exit 1; }
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    github_error 'issue branch already exists; refusing to overwrite or resume'; exit 1
fi
# get-url expands insteadOf/pushInsteadOf. Check all effective destinations and
# refuse multiple destinations, host aliases, local paths, and mismatched repos.
fetch_url=$(git remote get-url --all origin 2>/dev/null) || { github_error 'origin fetch destination is unavailable'; exit 1; }
push_url=$(git remote get-url --push --all origin 2>/dev/null) || { github_error 'origin push destination is unavailable'; exit 1; }
expected="$1/$2"
for destination in "$fetch_url" "$push_url"; do
    [[ "$destination" != *$'\n'* ]] || { github_error 'origin has multiple destinations'; exit 1; }
    identity=$(github_remote_identity "$destination") || { github_error 'origin is not a supported canonical GitHub destination'; exit 1; }
    [[ "$identity" == "${expected,,}" ]] || { github_error 'origin does not match the selected GitHub repository'; exit 1; }
done
# Capture Git diagnostics privately: a transport error may include credentials.
umask 077
scratch=$(mktemp -d "${TMPDIR:-/tmp}/lean-sdd-branch.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
failed() {
    printf 'ERROR: GitHub branch preparation failed during %s; current branch=%s, HEAD=%s; state preserved\n' \
        "$1" "$(git branch --show-current 2>/dev/null)" "$(git rev-parse --verify HEAD 2>/dev/null)" >&2
    exit 1
}
git switch "$WORKING_BRANCH" > "$scratch/git.log" 2>&1 || failed switch
git pull --ff-only origin "$WORKING_BRANCH" > "$scratch/git.log" 2>&1 || failed synchronization
SOURCE_COMMIT=$(git rev-parse --verify HEAD)
remote_commit=$(git rev-parse --verify FETCH_HEAD) || failed verification
[[ "$SOURCE_COMMIT" == "$remote_commit" ]] || failed synchronization-local-ahead
git switch -c "$BRANCH" > "$scratch/git.log" 2>&1 || failed creation
[[ "$(git branch --show-current)" == "$BRANCH" && "$(git rev-parse --verify HEAD)" == "$SOURCE_COMMIT" ]] || failed verification
jq -cn --arg owner "$1" --arg repo "$2" --argjson number "$3" --arg branch "$BRANCH" \
    --arg base "$WORKING_BRANCH" --arg commit "$SOURCE_COMMIT" \
    '{owner:$owner,repo:$repo,issue_number:$number,issue_reference:($owner + "/" + $repo + "#" + ($number|tostring)),
      BRANCH:$branch,WORKING_BRANCH:$base,SOURCE_COMMIT:$commit}'
