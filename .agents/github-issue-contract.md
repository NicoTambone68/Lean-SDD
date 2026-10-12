# GitHub issue and branch contract

## Inputs and entry points

Paths below are relative to the adopting project root. Every
entry point is Bash, exits nonzero on failure with concise stderr, and emits one
JSON object on stdout only for success. Require uv for environment loading,
Bash, jq, and curl for MCP, and Git for branch preparation. From the project root,
prefix each entry point below with
`uv run --no-project --env-file .agents/.env -- bash .agents/skills/`.
uv loads `GITHUB_MCP_URL` and `GITHUB_TOKEN` from the untracked environment file,
preserving values already exported. Bind explicit arguments before invoking uv;
do not source `.env` or returned data as arbitrary code. See
[environment setup](README.md#environment-and-capability-verification).
The shared transport owns MCP sessions, requests, timeouts, and cleanup. Issue
scripts use owning-shell calls with output redirected to private temporary files.

| Operation | Invocation after the uv/Bash prefix above | Success contract |
| --- | --- | --- |
| Discovery | `list-repositories/scripts/list-repositories.sh "$QUERY"` | query, normalized repositories, total_count, pages, incomplete_results/reasons |
| Create | `create-issue/scripts/create-issue.sh "$OWNER" "$REPO" "$TITLE" "$BODY"` | full normalized issue and returned database issue_id |
| Read | `get-issue/scripts/get-issue.sh "$OWNER" "$REPO" "$ISSUE_NUMBER"` | full normalized issue |
| Comment | `update-issue/scripts/comment-issue.sh "$OWNER" "$REPO" "$ISSUE_NUMBER" "$COMMENT"` | explicit issue identity, returned comment_id/comment_url |
| Close | `update-issue/scripts/close-issue.sh "$OWNER" "$REPO" "$ISSUE_NUMBER"` | explicit issue identity, returned issue_url, verified state=closed |
| Branch | `git-change-workflow/scripts/prepare-change-branch.sh "$OWNER" "$REPO" "$ISSUE_NUMBER" "$WORKING_BRANCH"` | owner, repo, issue_number, issue_reference, BRANCH, WORKING_BRANCH, starting SOURCE_COMMIT |

A normalized issue has `owner`, `repo`, positive numeric `issue_number`, returned
`issue_url`, complete `title`/`body`, observed `state`, optional observed
`updated_at`, `issue_reference=owner/repo#number`, and `BRANCH=gh-number`.
Numbers must be canonical positive decimal integers of at most 15 digits, within
jq's exact numeric range. Database issue/comment IDs remain strings. Missing or
null bodies fail; an actual empty string is preserved. GitHub URL identity is
checked case-insensitively against the explicitly selected repository.

`lib/github-identity.sh` contains lexical identity and canonical Git remote
validation. `lib/github-issues.sh` contains the narrow shared MCP domain decoder
and issue identity checks. Structured content must match the expected type
(object by default; pull-request helpers request arrays for PR/review lists).
Accompanying text, if present, must decode to that same value. Otherwise require
exactly one text JSON value of that type. Ambiguous representations are errors.

Discovery calls `get_me` then `search_repositories` with the exact caller query,
`minimal_output=false`, `perPage=100`, and successive pages. GitHub documents a
[1,000-result search boundary](https://github.com/github/docs/blob/main/content/rest/search/search.md).
Repeated results, changed totals, premature endings, server incomplete flags,
and that boundary are explicit reasons for incompleteness. Empty results are
valid. Repository records preserve owner/name/URL and optional visibility,
private, and archived metadata; they never assert write access or select a repo.

Branch preparation checks both effective fetch and push destinations using
`git remote get-url --all origin` and `git remote get-url --push --all origin`,
including Git's URL rewriting. Exactly one supported canonical GitHub URL each
must match the selected repository. SSH host aliases and local remotes are not
identity proof. The script never rewrites remotes or injects MCP credentials.
It requires attached HEAD, writable Git metadata, a clean worktree (including
untracked files), an existing local explicit base, and an absent issue branch.
It synchronizes only with `pull --ff-only`, rejects a local-ahead result, then
creates the branch at the fetched commit. Failures preserve and report actual
state, including when switching or fetching already happened. Git transport
errors are summarized because raw errors can expose credential-bearing URLs.

## Workflow gates

- After creation, stop for implementation approval; read the current issue anew
  and recheck the constitution before branch preparation. Preserve the full
  current plan and explicit owner/repo/number throughout.
- Use `update-issue/SKILL.md` templates for implementation, pull-request,
  finalization, and failure checkpoints, populated only with actual facts.
- Implementation checkpoint success precedes separate publication approval.
  Successful publication and PR checkpoint precede separate merge approval.
  Retain actual publication values, including the full implementation
  source SHA and explicit working branch, across the merge gate. The branch
  preparation SOURCE_COMMIT is only its starting commit.
- The merge script must use the schema-verified `expectedHeadSha` for the
  approved merge and verify the remote merge and local synchronization before
  finalization.
- Use non-closing `owner/repo#number` references in commits/PR descriptions.
  Closure remains a separate `update-issue` operation, invoked only after
  the finalization comment succeeds. A confirmed update alone is insufficient;
  targeted readback must confirm the same issue closed.
- A failed comment stops without recursive audit. Unconfirmed closure stops
  without assuming open/closed or adding a failure comment. Unknown create/write
  outcomes must be reconciled, never automatically retried.
