# Publication and merge contracts

## Exact JSON interfaces

Both entry points accept one readable JSON file as their sole positional
argument. Require exactly one object and the specified key set; missing/extra
fields, wrong types, NUL/control characters in identities, invalid refs/SHAs,
and inconsistent owner/repo/issue/branch mappings fail before mutation.

| Field | Type and meaning | Publication input | Retained merge input |
| --- | --- | --- | --- |
| `owner`, `repo` | Explicit GitHub repository slugs | Required | Same values |
| `issue_number` | Positive JSON integer, at most 15 decimal digits | Required | Same value |
| `issue_url` | Returned canonical GitHub issue URL matching owner/repo/number | Required | Same value |
| `BRANCH` | Exactly `gh-<issue_number>` | Required | Same value |
| `WORKING_BRANCH` | Explicit literal local branch name, distinct from BRANCH | Required | Same value |
| `SOURCE_COMMIT` | Full lowercase 40-digit GitHub source SHA | Approved implementation commit | Validated PR head SHA, equal to approved commit |
| `title`, `body` | Meaningful complete strings; newline/Unicode preserved | Required | Not present |
| `issue_reference` | Exact `owner/repo#number` | Derived for successful output | Required |
| `PR_ID` | Actual positive numeric PR number, not an opaque database ID | Returned from verified PR | Required |
| `PR_URL` | Returned canonical GitHub PR URL matching owner/repo/PR_ID | Returned from verified PR | Required |

Publication success is precisely the retained merge input. Keep its JSON file
unchanged across the checkpoint and approval gate. Preparing a new tuple from a
later HEAD or PR response would replace approved state and is forbidden.
`SOURCE_COMMIT` returned by B's branch preparation was its starting commit;
the publication input instead uses the actual validated implementation commit.

Merge success adds these factual fields to the retained tuple:

- `merged: true`: independently observed PR merge and verified commit.
- `merge_commit`: actual merge response SHA, independently checked; never
  substituted for SOURCE_COMMIT.
- `local_branch`: actual verified current branch, equal to WORKING_BRANCH.
- `local_commit`, `remote_commit`: equal full SHAs from local HEAD and the
  freshly fetched remote-tracking ref.
- `synchronized: true`, `clean: true`: verified Git postconditions.

Only a zero exit and complete success object permit a success checkpoint.
Stdout is reserved for that object; stderr contains concise diagnostics. The
scripts never load Python fixtures, source JSON, call direct REST/GraphQL, invoke
service CLIs, close issues, or submit audit comments.

## Preparing actual publication input

After implementation checkpoint and publication approval, the caller binds
`OWNER`, `REPO`, `ISSUE_NUMBER`, `ISSUE_URL`, `BRANCH`, `WORKING_BRANCH`,
`SOURCE_COMMIT`, `TITLE` and `BODY` to actual retained/approved facts. Use the
validated implementation commit, not the branch's starting SHA. The private
`PUBLICATION_INPUT` and `RETAINED_STATE` paths are outside the worktree.

```bash
umask 077
jq -n --arg owner "$OWNER" --arg repo "$REPO" \
    --argjson issue_number "$ISSUE_NUMBER" --arg issue_url "$ISSUE_URL" \
    --arg BRANCH "$BRANCH" --arg WORKING_BRANCH "$WORKING_BRANCH" \
    --arg SOURCE_COMMIT "$SOURCE_COMMIT" --arg title "$TITLE" --arg body "$BODY" \
    '{owner:$owner,repo:$repo,issue_number:$issue_number,issue_url:$issue_url,
      BRANCH:$BRANCH,WORKING_BRANCH:$WORKING_BRANCH,SOURCE_COMMIT:$SOURCE_COMMIT,
      title:$title,body:$body}' > "$PUBLICATION_INPUT" || exit 1
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/finalize-implementation/scripts/publish-implementation.sh \
        "$PUBLICATION_INPUT" > "$RETAINED_STATE" || exit 1
```

Record the PR checkpoint from this successful output and stop for separate merge
approval. Only then pass that identical retained file to the merge entry point;
never reuse `PUBLICATION_INPUT` as merge input or overwrite retained approval
state with a fresh observation.

## Publication sequence

1. Validate the entire input, title/body and canonical non-closing reference.
2. Require clean index/worktree (including untracked files), attached expected
   branch/HEAD, writable Git metadata, existing local working branch, canonical
   issue reference in the commit, and both effective origin destinations matching
   the repository. Reuse B's canonical SSH/HTTPS identity rules; no aliases or
   local-path bypass in production.
3. Initialize MCP, discover all tool schemas, validate phase capabilities, and
   successfully read `get_me`. Git credentials are separate.
4. Enumerate open PRs with explicit repository/head/base filters, 100 per page.
   Validate results and stop on an exact match with its actual number/URL. Detect
   repeated IDs/pages and fail at the 100-page completeness boundary.
5. Recheck local state; push the explicit approved SHA to `refs/heads/BRANCH`
   without force or implicit tag publication. Explicit SHA prevents a concurrent
   local branch move from selecting a different commit for this push.
6. Create with explicit repository/head/base/title/body. Validate the returned
   ID/URL, then read that PR and require its repository/head/base/SHA and open,
   non-draft, unmerged state to match. Recheck local state and emit the tuple.
7. Orchestration records B's PR checkpoint and waits for separate merge approval.

Closing-keyword detection is deliberately conservative, including Markdown link
and formatting variants. Reword flagged text; the script never silently rewrites
an approved description. Use ordinary non-closing issue references.

## Merge sequence and evidence limits

Initialize a new MCP session and recheck local/remote state and phase schemas.
Require the deployed `expectedHeadSha` input and merge-commit method. Read the
exact PR with matching head/base repository names, refs, source SHA, open state,
non-draft and unmerged flags. Require observed `mergeable_state=clean`.

Read combined statuses for the retained SHA, enumerate check runs and reviews,
and reject failed/pending/unknown observations or incomplete enumeration. All
observed check runs must be completed with success, neutral or skipped outcomes.
Latest substantive review per reviewer must not request changes; a later comment
does not dismiss a changes-requested review. Pending/unknown review states fail.
An old approval is not claimed to approve the current SHA. These observations do
not enumerate the repository's complete required-review policy.

A combined status of pending with zero contexts means no commit statuses were
observed; it is not reported as a successful check. Actual pending contexts
block. An empty check/review list is similarly an observation, not proof that
no required policy exists. GitHub's ordinary merge enforcement is authoritative;
this workflow cannot bypass protection. Truncated combined status data fails
because this deployed method does not expose status pagination. Checks/reviews
use 100-item pages, repeated-ID detection and a 100-page hard failure boundary.

Immediately before the request, recheck local state and read the exact PR again,
including base identity and mergeability. Send the retained source SHA as
`expectedHeadSha` and only `merge_method=merge`. The base may legitimately advance;
this safeguard does not lock all PR metadata or the base ref atomically.

Require a positive merge response with a full SHA. Independently read the PR
again, requiring matched identity, source, destination, `state=closed`,
`merged=true`, and observed `merged_at`. A closed PR alone is insufficient.
The deployed MCP minimal PR response omits `merge_commit_sha`; therefore C also
reads the exact returned SHA through MCP `get_commit` and checks its SHA and
repository commit URL. If a PR response includes `merge_commit_sha`, it must
agree. No merge SHA is inferred from the current base tip.

Fetch the explicit base into its tracking ref without a force refspec. Before
switching the local base, verify the returned merge is in the fetched ancestry,
is a two-parent commit whose second parent is SOURCE_COMMIT, and whose first
parent descends from the immediately observed base SHA. Then switch to the exact
working branch and fast-forward from that fetched tracking ref. Confirm current
branch, cleanliness, equal local/tracking SHAs and merge ancestry. Newer base
commits are accepted if those conditions hold. Fetch plus explicit `merge
--ff-only` binds synchronization to the verified fetched ref without another
network pull or an inferred upstream. Local-ahead or divergent state is not reset.

## Response evidence

Read-only evidence was collected from the configured official GitHub MCP endpoint
on 2026-09-13, using A's transport. `tests/fixtures/github-pr-schemas.json`
projects actual names/input schemas for get_me, PR list/create/read/merge and
get_commit. Public PR reads on `github/github-mcp-server#3254` verified minimal
head/base objects (`ref`, `sha`, `repo.full_name`), state/draft/merged flags,
mergeability, combined status, empty check runs, review arrays and commit reads.
The inspected PR was closed and unmerged; these reads are not merge acceptance.
An empty merged-PR selection from a list was not treated as merged evidence.

The official upstream [PR implementation](https://github.com/github/github-mcp-server/blob/main/pkg/github/pullrequests.go)
and [minimal types](https://github.com/github/github-mcp-server/blob/main/pkg/github/minimal_types.go)
provide source evidence for create `{id,url}`, merge `{merged,sha,message}`, PR
`merged_at`, statuses, checks and reviews. Upstream main is not proof of the
remote server's deployed revision. Write responses, source-race rejection and
resulting remote movement are fixture-tested; live writes remain for D in an
explicitly authorized disposable repository. No GitHub PR was created or merged
while implementing C.

Tests execute the real Bash phase scripts, reuse A's curl boundary, and operate
real local Git repositories against disposable bare remotes. Only effective
GitHub URL validation reads are substituted; Git operations still execute. The
MCP fixture explicitly advances the bare remote when delivering a simulated
server merge response. Constructing that fixture graph never replaces the
production `merge_pull_request` call. Events verify exact order and arguments,
not skill wording. Required validation remains pytest, Ruff lint/format, mypy,
Bash syntax checks and supplementary Bash linting when available.

## Failure and recovery handoff

| Failure | Known effects / permitted next step |
| --- | --- |
| Invalid input, dirty/mismatched state, missing tools/auth, existing PR | No publication/merge write; report evidence, stop for recovery decision |
| Push failure | Push outcome may be uncertain; no create, no force/retry |
| Create rejected/timed out/malformed | Push confirmed; create unconfirmed; inspect under an explicit recovery decision, never blindly create again |
| Created PR fails readback | Preserve known PR number and confirmed push; no publication success tuple/checkpoint |
| PR checkpoint fails | Preserve successful publication tuple and real PR; stop, no republish/merge |
| Changed/retargeted/ineligible PR or unmet observed conditions | No merge request; do not replace approved state or alter policy |
| Merge rejected/false/malformed/timed out | No second merge, no synchronization/checkpoint/closure; reconcile uncertain remote state explicitly |
| Merge readback/commit verification fails | Merge may have happened; stop before local synchronization |
| Remote evidence valid but fetch/ancestry/local synchronization fails | Preserve remote effects and local changes; report incomplete finalization, no reset/rollback/closure |
| Successful merge/sync result, then finalization comment fails | No issue closure; follow B's comment failure rules |

Diagnostics include stage, push/create/merge state, known PR number, whether PR
and commit reads verified remote evidence, and actual local branch/HEAD where
available. `remote_verified=true` does not claim local ancestry/synchronization
passed; the failing stage states what remains incomplete. The normal merge path
rejects already-merged PRs and cannot serve as a recovery command. Recovery is a
separate explicit orchestration decision, not an automatic retry mode.
