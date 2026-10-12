# GitHub MCP transport contract

## Required server capabilities

Verify the deployed tool schemas and authenticated identity before live
operations. Follow [setup](README.md) for verification commands. Input schemas
alone do not establish response fields or repository permissions.

| Required operation | Advertised tool and input contract |
| --- | --- |
| Repository discovery | `search_repositories`: `query`, `page`, `perPage` |
| Authenticated identity | `get_me`: empty arguments |
| Issue create/update | `issue_write`: `method` enum includes `create`, `update`; `owner`, `repo`, `issue_number`, `title`, `body` |
| Issue read | `issue_read`: `method=get`, `owner`, `repo`, `issue_number` |
| Issue close | `issue_write`: `method=update`, `state=closed`, `state_reason=completed`; verify afterward with `issue_read` |
| Audit comment | `add_issue_comment`: `owner`, `repo`, `issue_number`, `body` (do not use the reaction alternatives) |
| PR create | `create_pull_request`: `owner`, `repo`, `title`, `body`, `head`, `base` |
| PR read | `pull_request_read`: `method=get`, `owner`, `repo`, `pullNumber` |
| PR list | `list_pull_requests`: `owner`, `repo`, `head`, `base`, `state`, `page`, `perPage` |
| PR merge | `merge_pull_request`: `owner`, `repo`, `pullNumber`, `merge_method=merge`, `expectedHeadSha` |

`issue_write.method` advertises `create` and `update`. `issue_read.method`
advertises `get`, `get_comments`, `get_sub_issues`, `get_parent`, `get_labels`.
`pull_request_read.method` advertises `get`, `get_diff`, `get_status`,
`get_files`, `get_commits`, `get_review_comments`, `get_reviews`,
`get_comments`, `get_check_runs`.

`expectedHeadSha` is a string property in the actual merge input schema.
Although the server marks it optional, **the merge script must require the
retained approved SOURCE_COMMIT and always send it**. A preceding read cannot
replace that atomic expected-head safeguard.

## Transport interface

Source `lib/mcp.sh` once in the shell that owns the session. Public functions
return one JSON success object on stdout, concise diagnostics on stderr, and a
nonzero status on failure. Capture their stdout with redirection; do not put
public calls in command substitutions, pipelines, or background subshells.
The library checks the owning Bash process and rejects that misuse.

Bind `output_dir` to an existing private directory in the calling shell, then
load configuration into the Bash process that will own the MCP session:

```bash
uv run --no-project --env-file .agents/.env -- \
    bash -s -- "$output_dir" <<'BASH'
set -euo pipefail
output_dir=$1
source .agents/lib/mcp.sh
source .agents/lib/github-mcp.sh
umask 077
mcp_connect "$GITHUB_MCP_URL" "$GITHUB_TOKEN" > "$output_dir/initialize.json"
mcp_list_tools > "$output_dir/tools.json"
github_mcp_check_capabilities "$output_dir/tools.json"
mcp_call get_me '{}' > "$output_dir/identity.json"
# Reading completed output with $(jq ...) is safe: it changes no session state.
BASH
```

- `mcp_connect <endpoint> <token>` resets connection state, initializes, verifies
  the negotiated version and server metadata/tools capability, sends the
  initialized notification, then returns the complete initialize result.
- `mcp_list_tools` follows every cursor and returns `{"tools":[...]}` only after
  complete discovery. Repeated cursors, duplicate names, malformed pages and
  more than 100 pages fail; no partial list is emitted.
- `mcp_call <tool-name> <arguments-json>` accepts one JSON object, returns the
  **complete MCP tool result**, and does not parse text into domain data.
- `github_mcp_check_capabilities <tools-json-file>` checks the narrow input
  contract above. Its success object explicitly says write access is unverified.
  Missing tools, methods or fields block dependent operations. The integrated
  setup also runs `c_capabilities` for publication and merge from
  `lib/github-pr.sh` to check PR diagnostics/pagination and `get_commit`.

IDs are allocated before the HTTP subprocess runs, in the owning shell:
initialize uses 1; subsequent requests use 2, 3, etc. Notifications have no ID.
Each connection owns its optional session ID and negotiated protocol.

The supported protocol versions are `2025-06-18` (default) and `2025-03-26`.
An unknown or absent negotiated version is an error. The implementation follows
[MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
and [initialization](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle).
It supports plain JSON and terminated SSE message/default events, including
multiline data and CRLF. It validates one JSON-RPC envelope per message,
correlates responses, ignores unrelated events/notifications, and rejects
malformed/incomplete messages, duplicate matching responses, or server requests
for capabilities it does not advertise. It does not implement stream replay,
background listening, sampling, elicitation, or a general MCP SDK.

Requests use only the supplied HTTPS endpoint. Redirects and retries are
disabled, and curl's configuration file is disabled. `MCP_CONNECT_TIMEOUT`
(default 10) and `MCP_TIMEOUT` (default 30) accept integer seconds from 1 to 300.
`MCP_TOOLSETS`, when nonempty, is sent as `X-MCP-Toolsets`; any selection must
be verified again rather than assumed available. The verified configuration
uses the endpoint defaults. A GitHub MCP hostname is not a direct REST API.

Each HTTP subprocess owns a mode-0700 temporary directory and mode-0600
credential/payload files. Success, failure and handled interrupts clean those
files without replacing caller traps. As with any process, SIGKILL cannot run
cleanup. Callers must keep shell tracing off and protect their own success
output files, which can contain issue text. Tokens are not placed in curl's
argument vector; raw error bodies and curl diagnostics are never printed.

Network/HTTP, protocol, session, parsing and application errors propagate.
Failures invalidate the usable connection. An HTTP 404 requires an explicit
new connection before any later request. A write whose response is lost has
an **unconfirmed outcome**: no automatic retry or replay is attempted. The
error identifies the method/tool and request ID, without arguments or server
body. The orchestrator must stop and reconcile under its explicit policy.

## Shared domain contracts

These are **required normalized outputs**, not invented GitHub response schemas.
The issue and pull-request helpers map observed MCP results, including text
JSON or structured content, and must retain evidence for any newly consumed
server fields. Parse JSON as data with jq; never source or eval it. GitHub
service operations use only the configured official GitHub MCP server.

Identity inputs are explicit `owner`, `repo` and a positive integer
`issue_number`. Retain the returned issue URL. The human reference is
`owner/repo#number`; the issue branch is `gh-<issue-number>`. GitHub opaque IDs,
issue numbers and PR numbers are distinct. Never infer the repository from a
search hit, the issue from a branch, or `WORKING_BRANCH` from a default.

| Result | Fields the domain implementation must supply and validate |
| --- | --- |
| Issue | `owner`, `repo`, `issue_number`, `issue_url`, complete `title`, complete `body`, observed `state` |
| Comment | `owner`, `repo`, `issue_number`, returned `comment_id` |
| Discovery | `repositories` with returned identities/URLs; actual pagination and incomplete-result indication; never silently present partial results as complete |
| Publication | `owner`, `repo`, `issue_number`, `issue_url`, `PR_ID` (PR number), `PR_URL`, `SOURCE_COMMIT`, `BRANCH`, `WORKING_BRANCH` |
| Finalization | retained publication identity, verified `merged` result, actual `merge_commit`, actual local synchronization result and working-branch commit |
| Closure | explicit repository/issue identity and observed `state=closed`; otherwise an explicit unconfirmed outcome with nonzero exit |

Validate actual identities against requested/retained inputs, required field
presence and types, positive integer numbers, full specification text, returned
URLs and observed state before emitting success. Absent fields, `isError`,
wrong identity, malformed data or ambiguous output cannot become success.
Transport success alone does not establish domain success. Preserve approved
publication values literally across approval gates. Finalization must verify
both the remote merge and the actual local synchronization outcome; successful
write submission is insufficient to claim merge or closure.

## Validation and deployment prerequisites

Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy .`, and `bash -n` on the two library scripts. Production never
loads the fixtures or Python test code.

Remaining deployment prerequisites: explicitly selected GitHub repository,
appropriate token/policy access to that repository, separately working Git
SSH/HTTPS credentials, the applicable approvals and
verification of live operations. Repository provisioning and remote replacement
are outside this workflow.
