---
name: finalize-implementation
description: Publish an approved GitHub issue implementation or merge its separately approved PR using retained source identity and verified local synchronization.
---

Use the two Bash entry points for new GitHub projects. Read
[phase contracts and recovery boundaries](references/phase-contracts.md) before
invoking either phase. The integrated orchestration is in `AGENTS.md`;
authorized live acceptance remains pending. See [readiness](../../github-workflow-acceptance.md).

The caller supplies explicit owner/repository/issue identity and the working
branch retained from branch preparation. `BRANCH` must be `gh-<issue-number>`.
Never infer the issue from HEAD, default the base to `main`, or replace retained
values after an approval pause. Require `GITHUB_MCP_URL` and `GITHUB_TOKEN` in the
environment plus separate working Git authentication. Do not expose credentials.

Keep JSON input/output files in a protected location outside the Git worktree so
they survive approval pauses without making the implementation dirty. Use
`umask 077`; parse values with jq, never source/eval returned JSON. All inputs
must be actual values, not examples or placeholders.

## Publication invocation

Only after implementation, required validation, commit, implementation checkpoint
AND explicit publication approval:

```bash
bash .agents/skills/finalize-implementation/scripts/publish-implementation.sh \
    "$PUBLICATION_INPUT" > "$RETAINED_STATE"
```

The input file contains exactly `owner`, `repo`, `issue_number`, `issue_url`,
`BRANCH`, `WORKING_BRANCH`, `SOURCE_COMMIT`, `title`, and `body`.
`SOURCE_COMMIT` is the locally validated implementation commit approved for
publication, not the starting commit returned by branch preparation. The title
and full body must describe the approved implementation and actual validation.
Use a non-closing `owner/repo#number` reference in both commit and PR body.
Automatic closing links/keywords are rejected; reword flagged text explicitly.

The script checks local identity/cleanliness and both effective remote URLs,
rechecks MCP identity and tool schemas, enumerates existing matching PRs, pushes
the exact approved commit without force, creates a PR, and reads it back. An
existing matching open PR is a recovery stop, never an instruction to duplicate
or silently resume publication. MCP identity access does not prove write access.

Only exit 0 returns the retained publication tuple: `owner`, `repo`,
`issue_number`, `issue_url`, `issue_reference`, `PR_ID`, `PR_URL`, `SOURCE_COMMIT`,
`BRANCH`, and `WORKING_BRANCH`. Preserve these exact values and the entire JSON
file. Record B's pull-request checkpoint using this output. If that checkpoint
fails, keep the PR identity and stop; do not republish or merge.

After the checkpoint succeeds, report the PR and STOP for separate explicit
merge approval. Publication approval does not authorize merging.

## Merge invocation

Only after the pull-request checkpoint succeeds AND separate explicit approval
to merge the retained source commit:

```bash
bash .agents/skills/finalize-implementation/scripts/merge-implementation.sh \
    "$RETAINED_STATE" > "$FINALIZATION_RESULT"
```

Pass the exact successful publication file, not a record rebuilt from current
Git state. The script rejects a changed local HEAD, repository, branch, base,
PR head, or PR state, and rechecks authentication/capabilities after the pause.
It reads available statuses, checks, reviews and mergeability, then revalidates
the PR immediately before merging. Known failures, pending observed checks,
unknown mergeability, and changes requested by the latest substantive review
block the request. Required policy remains enforced by GitHub.

The only strategy is `merge_method=merge`, always with the literal retained
`expectedHeadSha`. No squash/rebase fallback, auto-merge, merge queue manipulation,
protection changes, or retries are performed. The guard applies to the source
SHA; it is not an atomic lock on the base or all PR metadata.

After the request, the script independently reads the PR and returned merge
commit through MCP, verifies Git merge parents/ancestry after fetching the exact
base, and synchronizes that local base by fast-forward only. A newer legitimate
base commit is allowed when it contains the verified merge.

Only exit 0 emits the retained tuple plus `merged`, `merge_commit`,
`local_branch`, `local_commit`, `remote_commit`, `synchronized`, and `clean`.
Record B's finalization checkpoint only from this successful output. Invoke B's
separate issue closure only after that checkpoint succeeds. Neither phase
records checkpoints, closes issues, or decides whether a human approved it.

## Failures

Nonzero exits stop the invocation and all dependent work. Diagnostics report the
failed stage, known push/create/merge state, known PR number, and local Git state.
Do not treat a transport acknowledgement as successful domain verification.

A create or merge timeout/malformed response can leave a real remote operation
unconfirmed. Never automatically repeat it or fabricate a success checkpoint.
If remote merge verification succeeded but local synchronization fails, preserve
the remote merge and local state, report incomplete finalization, and leave
closure blocked. Use B's failure checkpoint rules; never recursively audit a
failed comment. Recovery requires a separate explicit decision as documented in
the reference; these normal entry points do not implement a recovery mode.

## Successful handoff example

Use the exact input shapes and construction example in
[phase contracts](references/phase-contracts.md), with real retained values.
After publication approval, the publication invocation above writes
`RETAINED_STATE`; inspect it with `jq . "$RETAINED_STATE"`, record its checkpoint
and stop. After separate merge approval, pass that same file to the merge
invocation above and inspect `FINALIZATION_RESULT`. Only verified merge and
synchronization permit the finalization comment and separate closure. Keep both
files private outside the worktree; never execute sample identities as inputs.
