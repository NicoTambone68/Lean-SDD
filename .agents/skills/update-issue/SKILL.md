---
name: update-issue
description: Record GitHub workflow audit checkpoints through MCP and separately close an issue after successful finalization.
---

Use these scripts for all issue audit comments and closure. Require the retained
`OWNER`, `REPO`, and positive `ISSUE_NUMBER`; supply `GITHUB_MCP_URL` and
`GITHUB_TOKEN` in the environment. Never print credentials or evaluate returned
JSON as shell code.

```bash
bash .agents/skills/update-issue/scripts/comment-issue.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER" "$COMMENT"
```

The script validates the issue with `issue_read/get`, then calls
`add_issue_comment` with the exact text. Exit 0 returns `owner`, `repo`,
`issue_number`, `comment_id`, and `comment_url`. Record success only after this
result. Commenting never closes the issue or changes Git state.

Fill the following templates from actual operation outputs and repository state.
Omit unavailable optional facts; never invent IDs, URLs, commits, validations,
approvals, or states. References use non-closing `owner/repo#number` syntax. Avoid
closing keywords in commits and PR descriptions so merging cannot close the
issue before the finalization checkpoint.

## Implementation checkpoint

Only after implementation, required validation, and commit succeed:

```text
• Implemented and committed <description>.

  - Issue: <owner/repo#number>
  - Issue URL: <returned URL>
  - Branch: <gh-number>
  - Working branch: <retained working branch>
  - Commit: <actual full commit SHA>
  - <important implementation details>

  Validation passed:
  - <actual command and result>

  Publication awaits explicit user approval.
```

After the checkpoint succeeds, report the implementation and STOP for explicit
publication approval. Prior implementation approval does not authorize a push.

## Pull-request checkpoint

Only after approved publication and successful PR creation:

```text
• Pull request created successfully.

  - Issue: <owner/repo#number>
  - PR number: <actual returned PR number>
  - PR URL: <actual returned PR URL>
  - Branch: <retained branch>
  - Working branch: <retained working branch>
  - Source commit: <retained actual full source SHA>

  Merge and local working-branch synchronization await explicit user approval.
```

Retain the exact successful publication values across this gate. Do not repeat
publication or recompute the approved source commit. STOP for separate explicit
merge approval after this checkpoint succeeds.

## Finalization checkpoint

Only after the approved exact-source merge is verified, the retained local
working branch is synchronized with origin, and final repository checks pass:

```text
• Finalization completed successfully.

  - Issue: <owner/repo#number>
  - PR number and URL: <actual values>
  - Approved source commit: <retained full source SHA>
  - Merge commit: <verified actual full merge SHA>
  - Local <working branch> synchronized with origin/<working branch>
  - Working tree is clean and up to date.
```

Only after this comment succeeds may closure begin. Use the actual successful `finalize-implementation` result as evidence;
this comment script does not itself establish merge or synchronization.

## Failure checkpoint

If an operation fails after issue creation and before closure begins, stop
dependent work and comment using only facts known at that point:

```text
• Workflow stopped during <stage>.

  - Issue: <owner/repo#number>
  - Branch: <known branch, if available>
  - Working branch: <retained branch, if available>
  - PR number and URL: <known values, if available>
  - Stage: <failed step>
  - Error: <concise actual error>

  No further workflow actions will be performed.
```

Do not assert that the issue remains open unless a current read confirms that
state. Avoid logs or secrets in comments. After the comment succeeds, report the
failure and stop. If the comment script itself fails, report that error and stop;
never recursively audit or automatically retry an unconfirmed comment.

## Separate closure

Only after successful merge, synchronization, final checks AND finalization
comment, invoke:

```bash
bash .agents/skills/update-issue/scripts/close-issue.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER"
```

The script validates the target, calls `issue_write` with `method=update`,
`state=closed`, and `state_reason=completed`, then performs a targeted
`issue_read/get`. Exit 0 returns the verified identity, URL, and `state=closed`.
The workflow is complete only after that result.

A readback of the correct issue still open is a confirmed closure failure at the
time of that read. A denied, missing, malformed, timed-out, or mismatched response
leaves closure unconfirmed. In either case stop: do not blindly repeat the update,
assume the current state, or add a failure audit claiming the issue remains open.
The script does not infer whether orchestration prerequisites were completed;
the caller must enforce them. See [the B contract](../../github-issue-contract.md).

## Successful handoff example

With actual retained identity and a private `EVIDENCE_DIR`, write the relevant
checkpoint text above using only observed facts, then pass it literally:

```bash
COMMENT=$(cat "$EVIDENCE_DIR/checkpoint.txt")
bash .agents/skills/update-issue/scripts/comment-issue.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER" "$COMMENT" \
    > "$EVIDENCE_DIR/comment-result.json" || exit 1
jq '{owner,repo,issue_number,comment_id,comment_url}' "$EVIDENCE_DIR/comment-result.json"
```

A successful implementation/PR comment leads to its approval pause. A successful
finalization comment permits the separate closure invocation documented above.
