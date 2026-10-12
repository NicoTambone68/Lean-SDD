# GitHub issue and branch contract

## Inputs and entry points

Paths below are relative to the adopting project root. Every
entry point is Bash, exits nonzero on failure with concise stderr, and emits one
JSON object on stdout only for success. Require Bash, jq, and curl for MCP; Git
and jq for branch preparation. Set `GITHUB_MCP_URL` and `GITHUB_TOKEN` as protected
environment values. Do not source `.env` or returned data as arbitrary code.
A's transport owns MCP sessions, requests, timeouts, and cleanup; B uses owning
shell calls with output redirected to private temporary files.

| Operation | Invocation after `bash .agents/skills/` | Success contract |
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
(object by default; C explicitly requests arrays for PR/review lists).
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

## Historical evidence and tests

This section records original-port observations and tests. It is not evidence
that this installed project has been validated; referenced fixtures are not
bundled with the installer.

Read-only MCP verification on **2026-09-13 at 14:29 UTC** used the configured
official GitHub endpoint and A's transport. Successful calls were initialization,
`get_me`, `search_repositories` (`repo:github/github-mcp-server`, page 1, 100,
minimal output disabled), discovery of a public issue using `search_issues`, and
`issue_read/get` on `github/github-mcp-server#1`. No GitHub writes were performed.

Observed search fields: numeric `total_count`, boolean `incomplete_results`,
array `items`; each full repository included `owner.login`, `name`, `full_name`,
`html_url`, `visibility`, `private`, and `archived`. Observed issue fields:
`number`, `html_url`, `title`, `body`, `state`, and `updated_at`. The issue read did
not return `id` or `url`; these must not be fabricated or substituted for
`number`/`html_url`. The retained test fixture projects only those consumed
public fields; other account details, tokens, and session IDs are excluded.

Write-response fixtures are **source-informed and offline tested**, not live
write verification. GitHub's official
[issues.go](https://github.com/github/github-mcp-server/blob/main/pkg/github/issues.go)
implements create/update/comment responses using `MinimalResponse`: string `id`
and `url`. Issue URLs identify `/issues/<number>`; comment URLs include
`#issuecomment-<id>`. B validates these returned identities, then reads the exact
created/closed issue. That source is the upstream main branch, not proof of the
remote server's deployed revision. D must verify real write responses and
repository-specific access in an explicitly authorized disposable repository.
Unsupported or ambiguous write responses fail without retrying a mutation.

Tests run the real Bash entry points with A's curl/MCP boundary. They verify
literal multiline payloads, identity/entity rejection, empty versus absent body,
malformed/denied/timeout results, no duplicate create/comment/close, closure
readback, complete/partial/repeated search pages, and the 1,000-result boundary.
Git tests execute against disposable bare remotes. A test-only wrapper supplies
GitHub URLs for repository-validation reads; actual fetch/switch/fast-forward/
branch operations still use real Git. Production has no local-remote bypass.
The matrix covers main and non-main bases, remote advances, invalid/missing
inputs, dirty/detached/existing-branch states, wrong fetch/push destinations,
rewritten URLs, divergence/local-ahead, and operation failures.

Validation commands: `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run mypy .`, and `bash -n` for changed/new
Bash files. Production loads no Python tests or fixtures.

## C/D handoff and workflow gates

- After creation, stop for implementation approval; read the current issue anew
  and recheck the constitution before branch preparation. Preserve the full
  current plan and explicit owner/repo/number throughout.
- Use `update-issue/SKILL.md` templates for implementation, pull-request,
  finalization, and failure checkpoints, populated only with actual facts.
- Implementation checkpoint success precedes separate publication approval.
  Successful publication and PR checkpoint precede separate merge approval.
  C must retain actual publication values, including the full implementation
  source SHA and explicit working branch, across the merge gate. The branch
  preparation SOURCE_COMMIT is only its starting commit.
- C must use the schema-verified `expectedHeadSha` for the approved merge and
  verify the remote merge and local synchronization before finalization.
- Use non-closing `owner/repo#number` references in commits/PR descriptions.
  Closure remains a separate B operation, invoked only after the finalization
  comment succeeds. A confirmed update alone is insufficient; targeted readback
  must confirm the same issue closed.
- A failed comment stops without recursive audit. Unconfirmed closure stops
  without assuming open/closed or adding a failure comment. Unknown create/write
  outcomes must be reconciled, never automatically retried.
