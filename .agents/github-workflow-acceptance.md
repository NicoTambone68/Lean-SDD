# Integrated workflow evidence — lsdd-10

**Status: offline candidate; live acceptance pending.** Development integration
is not proof of new-project readiness. No disposable GitHub issue or PR has yet
been created for this acceptance. The candidate revision will be the actual
validated lsdd-10 implementation commit recorded in its workflow audit, not an
inferred branch tip or a self-referential value in this document.

## Reconciled inputs

The accepted dependencies were reread for integration: lsdd-7 (MCP foundation),
lsdd-8 (repository/issue/branch) and lsdd-9 (publication/merge/synchronization).
Their accepted implementation commits are respectively `9027928` (A),
`3d4feec34693bfc933709e86ff07409972577666` (B), and
`eff706dc6f53882f6bba93ba34c4f2bf8c174dc7` (C). Integration started from explicit
`feat` at `0075d35f37d21431fbc0128bb5836d6facee53df` after the C merge.
The actual scripts, rather than historical proposed file names, define the
interfaces described in [setup](README.md), [issue contracts](github-issue-contract.md)
and [phase contracts](skills/finalize-implementation/references/phase-contracts.md).

All six roles exist. The only runtime wiring change exposes C's existing
phase-specific schema validation as `c_capabilities <tools-file>`, reused by
both `c_connect` and the read-only deployment procedure. It does not change phase
inputs/results, consent policy, or service operations. A's nine-tool foundation
check alone could not establish C's `get_commit` and PR diagnostics requirements.

## Parent requirement traceability

Test paths below are relative to the port repository; they are verification
artifacts and never runtime dependencies. Each live cell is pending until the
corresponding actual disposable-project observation has been recorded.

| Parent requirement | Skill / real implementation | Proving offline test | Live evidence |
| --- | --- | --- | --- |
| MCP-only service operations and deployed contract | `lib/mcp.sh`, `lib/github-mcp.sh`, `lib/github-pr.sh:c_capabilities` | `test_mcp_transport.py`, `test_github_contracts.py` | A/C evidence plus D working-candidate read/schema checks passed; committed-candidate live run pending |
| Discover, then explicitly select repository | `list-repositories/scripts/list-repositories.sh` | `test_repository_discovery.py`; `test_github_workflow.py` discovery has no writes | Selected `NicoTambone68/test`; complete targeted discovery verified through candidate Bash script |
| Create actual issue, stop, reread revised plan | `create-issue`, `get-issue`, `AGENTS.md` stages 1–2 | `test_github_issues.py`; integrated revised-body fixture | Actual issue URL and implementation pause pending |
| Explicit base and mapped branch | `git-change-workflow/scripts/prepare-change-branch.sh` | `test_branch_preparation.py`; integrated `feat` and explicit `main` runs | Acceptance base explicitly `main`; actual branch evidence pending |
| Validate, non-closing commit, implementation checkpoint | `AGENTS.md` stage 3; `update-issue/scripts/comment-issue.sh` | `test_issue_checkpoints.py`; integrated validation/comment boundary failures | Source SHA/check results and actual publication pause pending |
| Publish exact source, verify PR, retain tuple | `finalize-implementation/scripts/publish-implementation.sh` | `test_github_publication.py`; integrated separate-process publication | Actual PR URL/source/base and merge pause pending |
| Guard approved merge, independently verify and sync | `finalize-implementation/scripts/merge-implementation.sh` | `test_github_finalization.py`; integrated exact expected-head argument and Git state | Actual guarded merge/remote SHA/local SHA pending |
| Finalization comment before separate close/readback | `update-issue/scripts/comment-issue.sh`, `close-issue.sh` | `test_issue_checkpoints.py`; integrated closure-last and no-close-on-failure assertions | Successful finalization comment and observed closed state pending |
| Explicit errors and no dependent operations | All Bash entry points; `AGENTS.md` failure protocol | Integrated boundary matrix, no recursive audit, no duplicate create/merge; A/B/C negative cases | Any live failure recorded with known effects and uncertainty |
| Coherent setup, six roles, source/test separation | `AGENTS.md`, six `SKILL.md` files, `README.md`, `.env.example` | `test_github_contracts.py`: executable interfaces, relative links, source dependencies, syntax; runtime endpoint/command traces | Candidate setup and actual agent instruction use pending |

The end-to-end fixture invokes each real Bash entry point in a fresh process,
uses local Git against a temporary bare remote, and simulates MCP responses at
the curl boundary. Its explicit test approval events are **not human consent**.
It checks that the revised issue text reaches the implementation, the retained
JSON survives the pause unchanged, and no dependent mutations follow failure.
Source inspection, operational traces and instruction review complement each
other; keyword checks alone do not establish runtime behavior. Existing focused
A/B/C tests retain detailed malformed response, pagination, identity, concurrency,
transport, secret-redaction and Git failure coverage.

## Instruction review

The integrated instructions were reviewed against D2's sequence: issue creation
and actual identity precede implementation approval; a fresh authoritative read
and Constitution Check precede an explicitly based branch; validation/commit and
a successful implementation audit precede publication approval; verified
publication and successful PR audit precede separate merge approval; immutable
retained state and expected-head guarding precede independently verified remote
merge and local synchronization; successful finalization audit precedes separate
close/readback. Failure comments use known facts, comment failures do not recurse,
and uncertain closure is not asserted open or closed. Live pauses still need
observation; this review is not a substitute for them.

## Read-only acceptance prerequisites observed

On 2026-09-13, the working candidate's actual Bash transport and setup checks
successfully initialized the official endpoint, enumerated tools, passed the
foundation and both phase capability checks, and read authenticated identity.
The negotiated protocol was `2025-06-18`; server version was
`github-mcp-server/remote-d2d339e31592ae3fd8fe9c5277c6b220f7d7bab9`.
The actual `list-repositories` script searched `repo:NicoTambone68/test` and
returned that exact repository with `incomplete_results=false`, `private=true`
and `archived=false`. This establishes discovery access only. It does not prove
write/merge permissions, repository newness, human acceptance, or a completed
workflow. No issue/PR/comment/merge/closure writes were made by this probe.
Git read authentication also succeeded, but a targeted `git ls-remote` returned
no `refs/heads/main`. The selected base does not yet exist remotely; establishing
it is an unresolved acceptance prerequisite. The probe did not initialize or
push a branch. The committed candidate still requires its identified live run.

## Authorized fresh-project acceptance procedure

The user supplied **`NicoTambone68/test`** and explicitly selected **`main`**.
Repository provisioning and constitutional amendment are not part of acceptance.
Before live writes, verify that it is a disposable NEW repository, required
credentials/policy access and local Git authentication are available, identify
the exact candidate commit, and obtain authorization to start its real workflow.
Repository/base selection by itself does not authorize that workflow's writes.

1. Record the candidate commit and use its actual skills/scripts in an isolated
   new-project worktree. Follow [setup](README.md), respecting that project's
   constitution and source boundary. Leave the port repository's production
   agent, configuration, artifacts and remote untouched. Do not promote the
   candidate into the port's production agent or import existing artifact history.
2. Record sanitized initialize/server/protocol/toolset and complete schema-check
   evidence, plus authenticated identity-read success. Verify repository discovery
   for the explicitly selected target. Identity access is not proof of writes.
3. With explicit authorization for live acceptance, create/read a small test issue
   using the candidate's real `create-issue` script. Its plan must describe the
   small fixture change and actual validation. Record the actual issue URL and
   **stop for actual implementation approval**. Let the user revise the issue.
4. Reread that exact issue as authoritative, recheck the constitution, prepare
   its `gh-number` branch from explicit `main`, implement the authorized fixture,
   run required checks, commit and record the implementation audit. Record actual
   source SHA/check results; **stop for actual publication approval**.
5. Publish with the candidate script, verify the PR, preserve the literal tuple
   and record the PR audit. Record actual PR URL/source/base, then **stop for
   separate actual merge approval**.
6. Pass the same retained tuple to the candidate merge script. Record guarded
   merge request success, independent remote confirmation, actual merge SHA and
   local/fetched-base equality/cleanliness. Only after its finalization audit
   succeeds, separately close and verify the exact issue's closed state.
7. Record all actual repository/issue/PR URLs, candidate/source/merge SHAs,
   selected base, sanitized capabilities and check results in the relevant audit.
   Do not retain credentials or session identifiers in tracked evidence. Do not
   delete branches/repositories or perform other unsolicited cleanup.

Development-issue implementation/publication/merge approvals are distinct from
all disposable acceptance approvals. Missing access, an unsuitable/non-new
repository or a pending approval stops the dependent live phase. Report exactly
what remains pending; offline passing does not satisfy parent step 10. Any live
failure follows the candidate's failure protocol, preserving uncertainty and
remote effects. The deliverable is not complete until the live workflow passes;
otherwise keep readiness explicitly pending.

## Validation evidence

The implementation audit records the exact candidate commit and actual results
of `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy .`, Bash syntax and skill validation. Tests run without credentials
or network and reject alternate service clients or unexpected endpoints.
No required check may be reported passed before it runs successfully.

Constitution Check: root I–IX PASS; additional src I and VIII PASS, II–VII NOT
APPLICABLE to service orchestration. Runtime remains Bash under src; tests are
the authorized non-source exception. Both constitutions and production root
configuration/instructions/agent are unchanged. This record makes no claim of
live acceptance, deployment, migration or promotion.
