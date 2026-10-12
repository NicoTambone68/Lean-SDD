---
name: create-issue
description: Create a GitHub issue with an explicit repository, meaningful title, and complete implementation plan through MCP.
---

Before execution, establish the user's selected `OWNER` and `REPO`. Prepare a
meaningful title and full Markdown plan, including relevant components, approach,
technical considerations, validation, and Constitution Check. Do not omit or
summarize the body when passing it to the script.

Run from the project root using uv to load `.agents/.env` as described in
[environment setup](../../README.md#environment-and-capability-verification).
Bind explicit arguments in the calling shell before invoking uv.

```bash
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/create-issue/scripts/create-issue.sh \
        "$OWNER" "$REPO" "$TITLE" "$BODY"
```

Provide `GITHUB_MCP_URL` and `GITHUB_TOKEN` through `.agents/.env` or the
existing environment; uv passes them to the script without printing the token.
Arguments are data; never use `eval`, source returned JSON, or interpolate
untrusted text as shell code. The script binds arguments with jq, calls
`issue_write` with `method=create`, validates the returned issue URL/database ID,
and reads the newly identified issue using `issue_read` with `method=get`.

Only exit 0 confirms success. Retain the returned `owner`, `repo`, `issue_number`,
`issue_url`, `issue_id`, `issue_reference` (`owner/repo#number`), and `BRANCH`
(`gh-number`). The database `issue_id` is not the issue number. No branch is
created by this skill.

Report the returned issue reference and URL, then STOP for explicit approval to
implement. The user may edit the issue during this gate. After approval, invoke
`get-issue` again with the retained owner, repository, and issue number; that fresh
read is the authoritative specification. Recheck the constitution before branch
preparation. Creation never grants publication or merge approval.

If the script fails, stop. A timeout, malformed result, sparse result without a
reliable URL, or failed readback can leave creation unconfirmed. Do not guess an
issue number, create a branch, or automatically repeat creation. Report known
identity and uncertainty for reconciliation; a second create can duplicate an
issue. See [the B contract](../../github-issue-contract.md).

## Successful handoff example

With actual explicitly selected `OWNER`/`REPO`, full reviewed `TITLE`/`BODY`,
and a private `EVIDENCE_DIR` outside the worktree:

```bash
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/create-issue/scripts/create-issue.sh \
        "$OWNER" "$REPO" "$TITLE" "$BODY" > "$EVIDENCE_DIR/issue.json" || exit 1
jq '{issue_reference,issue_url,issue_number,BRANCH}' "$EVIDENCE_DIR/issue.json"
```

Report those returned values and stop for implementation approval. This is a
template for actual values, not permission to create an example issue.
