---
name: get-issue
description: Retrieve and validate the full current GitHub issue specification for an explicitly expected repository and issue number.
---

Require the expected `OWNER`, `REPO`, and positive `ISSUE_NUMBER` from the retained
issue identity. Do not infer these from the current branch or a database ID.

```bash
bash .agents/skills/get-issue/scripts/get-issue.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER"
```

Provide `GITHUB_MCP_URL` and `GITHUB_TOKEN` in the environment. The script calls
`issue_read` with `method=get` through A's HTTP MCP transport. It validates the
returned number, GitHub issue URL, entity type, title, complete body, and state.
It rejects pull requests, identity mismatches, missing/null body, inaccessible
issues, malformed responses, and transport failures.

Exit 0 emits JSON with `owner`, `repo`, `issue_number`, `issue_url`,
`issue_reference`, `BRANCH`, `title`, `body`, `state`, and `updated_at` if observed.
An empty string body is valid and remains empty; a missing body is an error.
Return the full body without truncation. Treat values as data, never shell code.

After implementation approval, perform a fresh read and use it as the complete
authoritative specification. Revalidate the constitution. If the fresh body does
not specify enough work to implement safely, clarify the missing requirement;
do not substitute a remembered plan. A nonzero exit blocks dependent operations.
See [the B contract](../../github-issue-contract.md).

## Successful handoff example

After implementation approval, bind identity from the retained successful issue
file in the private `EVIDENCE_DIR`, then read the revised specification:

```bash
OWNER=$(jq -er .owner "$EVIDENCE_DIR/issue.json")
REPO=$(jq -er .repo "$EVIDENCE_DIR/issue.json")
ISSUE_NUMBER=$(jq -er .issue_number "$EVIDENCE_DIR/issue.json")
bash .agents/skills/get-issue/scripts/get-issue.sh \
    "$OWNER" "$REPO" "$ISSUE_NUMBER" > "$EVIDENCE_DIR/current-issue.json" || exit 1
jq '{issue_reference,title,body}' "$EVIDENCE_DIR/current-issue.json"
```

Recheck that full plan against the constitution before preparing its branch.
