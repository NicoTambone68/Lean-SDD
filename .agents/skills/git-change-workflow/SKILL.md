---
name: git-change-workflow
description: Prepare gh-number from an explicitly selected working branch and verify that origin targets the selected GitHub repository.
---

Use only after implementation approval, a fresh successful `get-issue` read, and
Constitution Check. Require the retained `OWNER`, `REPO`, and `ISSUE_NUMBER` plus
the exact `WORKING_BRANCH` explicitly supplied by the user. Never infer a base,
default to `main`, derive identity from HEAD, or execute placeholder values.

```bash
bash .agents/skills/git-change-workflow/scripts/prepare-change-branch.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER" "$WORKING_BRANCH"
```

The script validates inputs, attached HEAD, writable Git metadata, a clean
worktree including untracked files, a local working branch, and absence of
`gh-<issue-number>`. It checks Git's expanded effective origin fetch AND push
URLs. Both must identify the selected GitHub owner/repository; multiple
destinations, host aliases, local paths, and mismatches fail before switching.
Canonical HTTPS, `git@github.com:owner/repo.git`, and
`ssh://git@github.com[:22]/owner/repo.git` URLs are supported. Git authentication
remains the user's Git setup; the MCP token is not written into remotes.

It switches to the exact working branch, pulls `--ff-only` from origin, verifies
that local HEAD equals the fetched branch, and creates `gh-<issue-number>` at
that commit. Local-ahead and divergent bases fail without resetting history.
Failures report the stage and actual local state; no rollback, branch overwrite,
remote rewrite, commit, push, or audit comment is hidden in the script.

Only exit 0 permits implementation. Retain the successful JSON fields `owner`,
`repo`, `issue_number`, `issue_reference`, `BRANCH`, `WORKING_BRANCH`, and
`SOURCE_COMMIT` (the branch's starting commit). Later publication must retain its
own actual implementation source commit; do not confuse it with this starting
commit. Carry the same working branch through publication and synchronization.

Use non-closing traceability in implementation commits, for example
`Implement repository selection. octocat/example#42`. GitHub issue numbers are
repository-scoped; `gh-42` alone does not identify a repository. Never add an
automatic closing keyword to a commit or PR description; closure is a separate
post-finalization operation. On failure, use `update-issue` for the failure
checkpoint, then stop. See [the B contract](../../github-issue-contract.md).

## Successful handoff example

With retained actual issue identity, the explicitly selected `WORKING_BRANCH`
and a private `EVIDENCE_DIR` outside the worktree:

```bash
bash .agents/skills/git-change-workflow/scripts/prepare-change-branch.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER" "$WORKING_BRANCH" \
    > "$EVIDENCE_DIR/branch.json" || exit 1
jq '{issue_reference,BRANCH,WORKING_BRANCH,SOURCE_COMMIT}' "$EVIDENCE_DIR/branch.json"
```

Only this successful result permits edits. Retain the base unchanged; obtain
the later implementation SHA only after its validation and commit.
