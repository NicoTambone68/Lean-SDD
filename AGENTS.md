# GitHub issue workflow for new projects

This agent governs the issue-driven workflow for a supplied GitHub project.
Repository provisioning, remote replacement, and history migration are separate
work and are not authorized by this workflow. See
[setup and readiness](.agents/README.md) before starting live operations.

## Constitution and scope

Read the project's [CONSTITUTION.md](CONSTITUTION.md) and
[CODING_STANDARDS.md](CODING_STANDARDS.md) before planning or modifying files.
The constitution defines engineering invariants; the coding standards define
concrete Python rules. This file owns workflow orchestration and enforces those
rules without duplicating or overriding them. Include a Constitution Check
classifying each principle as PASS, NOT APPLICABLE, or VIOLATION with a concise
justification, and identify applicable coding standards. A violation blocks
implementation: identify the principle, record a failure checkpoint if an issue
is already known, and STOP.
Never amend or bypass the constitution without an explicit amendment request.
Read both rule documents again against the complete freshly retrieved issue
after approval.

Check the proposed file scope against Constitution principle III before
implementation. A source-boundary violation blocks implementation; apply the
failure handling below when an issue is already known.

Read-only requests do not require an issue. If investigation leads to a change,
follow the issue workflow before modifying files. Use one repository-scoped
issue and one issue branch per implementation unless explicitly instructed
otherwise. Orchestration and human decisions live here; Bash skills perform
individual deterministic operations, without approval flags or an automatic
workflow engine.

## Identity and setup

Obtain explicit `OWNER` and `REPO` selection and the user's exact working/base
branch `WORKING_BRANCH`. Discovery through `list-repositories` helps the user
choose; search results never select a repository or authorize provisioning.
The working branch is mandatory. Never infer it from HEAD or default to `main`;
`main` is valid only when explicitly selected. Preserve the selection through
branch preparation, publication, merge and final local synchronization.

Use the six skills under `.agents/skills/` and their Bash entry points. GitHub
service operations use only the configured official GitHub MCP server. Git
operations use local Git with separate credentials. Verify deployed tool schemas
and identity as described in setup; identity reads do not prove write access or
Git push permission. Unsupported tools stop dependent work without fallback.

Invoke every skill's Bash entry point from the project root with the prefix
`uv run --no-project --env-file .agents/.env -- bash`, as shown in each skill.
Follow [environment setup](.agents/README.md#environment-and-capability-verification)
to prepare the untracked `.agents/.env`. uv loads configuration for the child
process; do not read secret values into the conversation or source the file as
shell code. Bind selected repository/base and retained issue/PR arguments in the
calling shell before invoking uv; `.env` does not select those identities.
A failed uv invocation stops dependent work just like a failed skill script.

Retain `owner`, `repo`, `issue_number`, `issue_url` and `issue_reference` from
successful issue results. The canonical reference is `owner/repo#number`; the
branch is `gh-<issue-number>`. The issue database ID, issue number and PR number
are distinct. Never infer an issue from a branch or use a number without its
repository. Check returned identities against expected values.

Store result JSON outside the worktree in a private, durable location across
pauses (`umask 077`). Parse JSON as data with jq; never source/eval it. Keep
credentials and shell tracing out of logs. Examples are templates: never execute
placeholder identities. A nonzero skill exit is a failure, even with partial
stdout or a successful transport status.

## 1. Create the issue and stop for implementation approval

Prepare a meaningful title and complete plan: requested behavior, components,
approach, technical considerations, validation, Constitution Check, and
applicable coding standards. Invoke `create-issue` with explicit owner/repository
and the complete title/body.
Wait for successful creation and targeted readback. Do not modify repository
files or prepare a branch before a verified issue identity exists.

If creation fails or its result cannot identify the created issue reliably,
report known facts and uncertainty, then STOP. Never guess an ID or automatically
repeat creation. If a reliable issue identity is known, follow failure handling
below without inventing a successful creation checkpoint.

Report the actual issue reference and URL, then **STOP for explicit implementation
approval**. The user may edit the issue while paused. After approval, invoke
`get-issue` with the exact retained owner/repository/number. The fresh full title
and body are authoritative; never substitute the remembered plan. Recheck the
constitution and applicable coding standards. Clarify an insufficient plan
before dependent work.

If the user explicitly requests implementing an existing issue, retrieve and
validate that exact issue instead of creating a duplicate. That request may
supply implementation approval; it never supplies later publication/merge gates.

## 2. Prepare the issue branch and implement

After the fresh read, passing Constitution Check, and explicit base selection,
invoke `git-change-workflow` with `OWNER REPO ISSUE_NUMBER WORKING_BRANCH`.
Require exit 0 before implementation. It verifies a clean attached worktree,
writable Git metadata, selected repository in both effective origin fetch and
push URLs, synchronizes the exact local base with `pull --ff-only`, then creates
`gh-<issue-number>`. It never overwrites an existing issue branch or resets a base.

Retain its `BRANCH` and `WORKING_BRANCH`. Its `SOURCE_COMMIT` is the starting
commit, not the eventual implementation commit. Implement only the current
approved issue in accordance with `CONSTITUTION.md` and `CODING_STANDARDS.md`.

## 3. Validate, commit and record implementation

Run all required checks in the project root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Fix implementation-related failures within scope and rerun affected checks.
Do not disable or weaken tests to pass. If a required failure cannot reasonably
be fixed within scope, record validation failure and STOP without staging or
committing. Inspect the diff and stage only issue files, excluding unrelated
pre-existing changes. Commit using `<Meaningful message>. owner/repo#number`.
Never use automatic issue-closing keywords in commits or PR text; closure must
remain a separate verified operation after finalization.

Capture the actual validated implementation commit from Git. Invoke
`update-issue` for the implementation checkpoint with issue, branch, selected
base, commit, implementation details and actual validation results. Only after
that comment succeeds report those facts and **STOP for explicit publication
approval**. Do not push, create a PR, merge, rebase, delete branches or close the
issue. Implementation approval does not authorize publication.

## 4. Publish, retain the PR result and stop for merge approval

After successful implementation checkpoint and explicit publication approval,
read `finalize-implementation` and its phase contracts. Build publication input
from the retained issue/repository/base, actual approved implementation commit,
and meaningful title/full body with non-closing canonical issue reference.
Invoke `publish-implementation.sh` once with that JSON file.

The skill verifies local identity, source, cleanliness, effective remotes and
MCP capabilities, checks for an existing matching PR, pushes the exact source,
creates the PR and verifies its returned identity/head/base. On failure follow
the failure rules, preserving known remote effects. Never automatically retry
an uncertain create or republish an existing PR.

Only successful exit returns the exact retained tuple:
`owner`, `repo`, `issue_number`, `issue_url`, `issue_reference`, `PR_ID`, `PR_URL`,
`SOURCE_COMMIT`, `BRANCH`, `WORKING_BRANCH`. Keep the entire successful JSON
unchanged across process/session pauses. Record the `update-issue` pull-request
checkpoint from these values; a comment failure stops without republishing.

Report the PR number/URL, source branch, selected base and approved source commit,
then **STOP for separate explicit merge approval**. Silence, earlier unrelated
approval, implementation approval or publication approval cannot satisfy this
gate. Do not invoke the merge phase until that approval arrives.

## 5. Merge the approved source and synchronize the selected base

Pass the exact retained publication file to `merge-implementation.sh`. Do not
rebuild it from HEAD, a PR listing, or a newly observed source. Missing, stale,
ambiguous or mismatched retained state requires a stop and explicit recovery;
new observations compare with approved values and never replace them.

The skill revalidates local identity and MCP capabilities, reads current PR
identity/head/base and policy diagnostics, and sends the retained source as
`expectedHeadSha` to `merge_pull_request`. It verifies the merged PR and merge
commit, then fetches the retained base, verifies merge ancestry, switches to that
local base and synchronizes with `merge --ff-only`. Require a clean worktree,
local/fetched-base equality and merge ancestry. An empty check/status set means
none observed; server policy remains authoritative. Unsupported expected-head
protection, blocked/pending/unknown checks or mergeability fail closed.

A successful remote merge alone is not finalization. If remote confirmation or
local synchronization fails, preserve actual effects, report the distinction
and STOP. Do not reset history, automatically rebase, delete branches or claim
rollback. Any later promotion to another branch is outside this workflow.

## 6. Finalization checkpoint, separate closure and completion

Only after verified merge, local selected-base synchronization and final clean
checks succeed, record the `update-issue` finalization checkpoint with the
retained issue/PR/source/base, verified merge commit and actual local/remote
commits. Require successful comment exit before any closure attempt.

Then invoke `update-issue`'s separate `close-issue.sh` with the retained issue
identity. It updates the issue and reads that exact issue back. Only exit 0 with
observed `state=closed` completes the workflow. Never close after a failed or
partial workflow or before the finalization comment succeeds.

## Failure handling at every boundary

After a known issue exists and before closure begins, stop dependent operations
when a required operation fails. Use `update-issue` to record one failure
checkpoint with only known issue/branch/base/PR/source facts, failed step and
concise actual error. Distinguish unattempted operations from uncertain or
verified remote effects. Do not assume the issue is still open without a current
read. After successful failure audit, report and STOP for recovery instructions.

If any audit comment fails, report that error and STOP: no recursive failure
comment, automatic retry or dependent operation. If closure fails or cannot be
confirmed, report the observed failure or uncertainty and STOP. Do not assume
open/closed state or append a failure checkpoint claiming it remains open.
Never hide a failed operation, recompute retained approval state, or continue on
partial results. Report a workflow checkpoint only after its operation succeeds.
