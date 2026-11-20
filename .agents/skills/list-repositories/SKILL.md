---
name: list-repositories
description: Discover GitHub repositories through MCP using an explicit search query or owner scope.
---

Use this skill when the user needs to identify a repository for a new GitHub
workflow. Require an explicit meaningful query, for example `user:octocat`,
`org:example`, or `repo:octocat/example`; never silently choose a repository.

Run from the project root using uv to load `.agents/.env` as described in
[environment setup](../../README.md#environment-and-capability-verification).
Bind explicit arguments in the calling shell before invoking uv.

```bash
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/list-repositories/scripts/list-repositories.sh "$QUERY"
```

uv loads `GITHUB_MCP_URL` and `GITHUB_TOKEN` from `.agents/.env` while preserving
existing environment values. Never print the token. The script uses the shared
HTTP MCP transport and `get_me` followed by `search_repositories`; no CLI or direct
API fallback is provided.

Exit 0 emits JSON containing `query`, `repositories`, `total_count`, `pages`,
`incomplete_results`, and `incomplete_reasons`. Each repository has `owner`,
`name`, and returned `url`; `visibility`, `private`, and `archived` are included
only when actually present. Visibility is not evidence of write permission.

An empty array is a valid empty search. Pagination requests up to 100 items per
page and stops at completion or GitHub's 1,000-result search boundary. Server
incompleteness, changing totals, premature endings, repeated results, and the
search boundary are explicitly reported. When incomplete, report that limitation
and narrow the query if needed; do not describe the output as an exhaustive list.

Malformed responses, inaccessible tools, or transport failures exit nonzero with
stderr diagnostics and no successful JSON. Stop and report the failure.

Retain the selected `owner` and `repo` explicitly for subsequent skills. See
[the issue and branch contract](../../github-issue-contract.md) for response
validation and repository selection requirements.

## Successful handoff example

For the user's actual owner scope, with a private `EVIDENCE_DIR`:

```bash
QUERY="user:$OWNER"
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/list-repositories/scripts/list-repositories.sh \
        "$QUERY" > "$EVIDENCE_DIR/repositories.json" || exit 1
jq '{repositories,incomplete_results,incomplete_reasons}' "$EVIDENCE_DIR/repositories.json"
```

Present the returned candidates and limitations for explicit selection. Do not
use this example's scope when the user supplied a different query.
