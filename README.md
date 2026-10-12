# Lean-SDD — GitHub Agent-Assisted Development

Lean-SDD provides an issue-driven development workflow for coding agents working
on Python projects. It connects a written specification to implementation,
validation, human review, and verified completion through GitHub issues and
pull requests.

## Introduction: Specification Driven Development

Specification Driven Development (SDD) starts with an explicit description of
what software should do, why it is needed, and how success will be verified.
That specification guides the implementation plan, code, tests, and review.
It remains a shared reference as the work evolves, making assumptions and scope
visible before they become implementation decisions.

This matters especially when coding agents generate changes quickly. A clear
specification gives the human and the agent a common target, reduces ambiguity
and unnecessary work, and provides a basis for judging whether the result
satisfies the request. Speed is useful when the intended outcome and the
acceptance criteria are understood.

### A lean approach for small projects

Lean-SDD is a deliberately lean implementation of SDD, suited to small projects
that need a clear plan, traceable changes, and human control with limited process
overhead. It intends to be **LLM agnostic**: the workflow is expressed in
repository documents and callable skills, so it can be followed by different
coding agents capable of honoring those instructions and invoking the tools.

It also aims to be **as system agnostic as practical**. Skills use Bash scripts
and common command-line tools rather than a model-specific runtime. Portability
still requires uv, a compatible Bash environment, Git, curl, and jq; the current
service integration targets GitHub MCP, and the supplied engineering rules and
validation commands target Python projects.

Although conceived for Python projects, Lean-SDD can be readily adapted to any
programming language by updating `CONSTITUTION.md`, `AGENTS.md`, and
`CODING_STANDARDS.md` for that language and its toolchain. The issue-driven
workflow and GitHub integration are independent of the application language.
See [adapting to another language](#adapting-to-another-language) for the
supporting configuration and documentation to review.

Other, more sophisticated SDD tools and frameworks are available and may be
better suited to your application, team size, or process requirements. Lean-SDD
keeps its scope small. It borrows the principle of a project **constitution**
from [GitHub Spec Kit](https://github.com/github/spec-kit): explicit engineering
principles that guide planning, implementation, and review. In this project,
those principles live in [CONSTITUTION.md](CONSTITUTION.md), with concrete Python
rules in [CODING_STANDARDS.md](CODING_STANDARDS.md).

### Issues as Kanbans and automation under human control

Lean-SDD adapts ideas from the **Toyota Production System** to software
development. Toyota describes a system organized around producing what is
needed and building quality into the process, including stopping when an
abnormality is detected. See Toyota's description of
[the production system and jidoka](https://global.toyota/en/company/vision-and-philosophy/production-system/).

In Lean-SDD, **issues function as Kanbans**: visible work items that define and,
once approved, authorize a bounded piece of development. The issue contains
the implementation plan, including intended behavior, scope, approach, and
validation. **No development begins without a related issue and approval of
its plan.** The issue then carries the checkpoints linking the specification
to the implementation, pull request, and verified completion.

The workflow applies **autonomation (jidoka)** as automation under human
control. Routine operations can proceed within an approved phase, while failed
checks, uncertainty, and approval boundaries stop dependent work. Human review
authorizes each major transition: implementation of the issue plan, publication
of the validated result, and merge of the reviewed source revision. Every step
remains within that approved scope and must satisfy its checks before the next
step proceeds. The three explicit approval gates are detailed below.

## Implementation overview

The agent coordinates the work and pauses for human decisions. Repository-local
Bash skills perform individual operations. All GitHub service operations use
the configured official GitHub MCP server; local Git handles branches, commits,
fetching, pushing, and synchronization with separate Git credentials.

## Install the CLI

The installer requires Python 3.11 or newer and uv. From a checkout of this
repository, install the CLI into uv's isolated tool environment:

```bash
uv tool install .
lean-sdd --version
```

If the executable directory is not on your PATH, run `uv tool update-shell`
and restart your shell. A built wheel can also be installed with
`uv tool install /path/to/lean_sdd_cli-0.1.0-py3-none-any.whl`.
The package has not been published to PyPI; installation by the bare name
`lean-sdd-cli` is not an advertised installation method yet.

Initialize a separate target project:

```bash
lean-sdd init /path/to/project --dry-run
lean-sdd init /path/to/project
lean-sdd doctor /path/to/project
```

Both commands default to the current directory when the path is omitted.
`init` installs the governing documents, six skills, shared Bash libraries,
configuration example, and setup references. It creates missing directories,
preserves identical existing files, and refuses the entire operation before
writing if any managed file conflicts. It rejects symbolic links in destination
paths. There is no overwrite flag or automatic upgrade; compare a fresh install
in a separate directory when adapting existing project rules. Do not modify the
target concurrently during initialization.

The installer records the template version and original file hashes in
`.agents/lean-sdd-install.json`. Commit this record with the installed workflow.
It also adds `.agents/.gitignore` to exclude local environment files and logs.
Existing `.env`, project README, application files, and Git configuration are
preserved. Installation does not provision a repository, select a working
branch, create issues, scaffold an application, or contact GitHub.

`doctor` checks installed files, local prerequisites, exported MCP configuration,
and basic Python project metadata. It never loads `.env`, runs project scripts,
or makes network requests. Modified templates and missing optional setup are
reported as warnings; missing required tools, missing workflow files, or an
invalid installation record are failures. Exit status is 0 without failures,
1 for an operational failure, and 2 for invalid command syntax. Warnings and a
successful local diagnostic do not establish live GitHub readiness.

Skill invocations require uv for environment-file loading and Bash 4 or newer
plus Git, curl, jq, awk, grep, and mktemp. On Windows, use a compatible
environment such as WSL for the complete workflow; installing the Python CLI alone does not supply these prerequisites.

## Principles and responsibilities

The workflow preserves traceability, reproducibility, explicit failures, and
human authority over project intent and consequential development decisions.
Each implementation uses one repository-scoped issue and one issue branch,
unless the user explicitly selects a different scope.

Three documents have distinct responsibilities:

| Document | Responsibility |
| --- | --- |
| [CONSTITUTION.md](CONSTITUTION.md) | Engineering invariants, constitutional checks, and amendment governance. |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Concrete Python coding, testing, packaging, security, and quality rules. |
| [AGENTS.md](AGENTS.md) | Workflow orchestration, approval gates, operation order, and failure handling. |

This README explains the system and its setup; it does not replace those
contracts. Skills describe their individual inputs, outputs, and failure
conditions. Shared Bash libraries implement reusable transport and validation.
Human approval decisions remain in orchestration rather than in script flags
or an automatic workflow engine.

Read-only investigation does not require an issue. Once investigation leads
to a requested change, the issue workflow applies before files are modified.
Constitutional amendments require explicit user approval.

## Repository layout

The repository contains the installer and the authoritative workflow files:

```text
.
├── README.md
├── AGENTS.md
├── CONSTITUTION.md
├── CODING_STANDARDS.md
├── .gitignore
├── pyproject.toml                # CLI packaging and development tools
├── uv.lock
├── src/lean_sdd/                 # installer, diagnostics, resource overrides
├── tests/                       # installer and distribution tests
└── .agents/
    ├── README.md                  # detailed setup and capability verification
    ├── .env.example               # non-secret configuration template
    ├── github-mcp-contract.md
    ├── github-issue-contract.md
    ├── lib/                      # shared Bash MCP and GitHub helpers
    └── skills/
        ├── list-repositories/
        ├── create-issue/
        ├── get-issue/
        ├── git-change-workflow/
        ├── update-issue/
        └── finalize-implementation/
```

Each skill has a `SKILL.md` and Bash entry points under `scripts/`.
The Python CLI installs this bundle; the workflow operations remain Bash.
There is no `.agents/tools/` Python project. The CLI has no third-party runtime
dependencies and lives in its isolated uv tool environment; an adopting
application manages its own Python environment separately.

An adopting Python project additionally supplies its application code under
`src/`, tests, `pyproject.toml`, and dependency lockfile. Those application and
test artifacts are not generated in the target by the installer. The tests in
this repository exercise the installer itself. Installed projects receive a
readiness checklist for verifying their own setup.

## Python project management with uv

**Python projects managed with Lean-SDD are tailored to use `uv`** for dependency
management, project environments, and execution of development tools. The
validation commands in `AGENTS.md` already use `uv run` consistently.

Lean-SDD adopts `uv` as a modern, well-suited choice for this workflow: it brings
Python version management, dependency resolution, virtual environments, and
project commands into one tool, with support for Linux, macOS, and Windows.
These capabilities keep setup small and repeatable for both developers and
coding agents. See [Astral's uv overview](https://docs.astral.sh/uv/) for its
supported features.

In an adopting project, declare metadata and dependencies in `pyproject.toml`,
commit `uv.lock`, and keep the generated `.venv/` out of version control. The
lockfile records resolved dependency versions for consistent installations.
See [uv project structure and files](https://docs.astral.sh/uv/concepts/projects/layout/).

Use `uv sync` to synchronize the project environment and `uv run` to execute
project commands. Both normally update the lockfile and environment as needed;
when validation must reject changes to the lockfile, use their `--locked`
option. See [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
for the exact behavior. Declare pytest, Ruff, and mypy as development dependencies
for the supplied Python validation workflow.

## Workflow and approval gates

**Code created or modified by the agent is never merged automatically.** After
publication approval, the agent creates a pull request for human review. The
user must explicitly instruct the agent to merge the retained source revision.
This instruction satisfies the workflow's merge approval gate. GitHub review
requirements are enforced separately under repository policy; a GitHub
"Approve" review alone does not instruct the agent to merge. Passing tests or
approval to publish also does not authorize a merge. While a review decision is
pending, the pull request remains unmerged; silence is not approval.

The normal lifecycle has **three separate human approval gates**:

```text
Request + explicit repository and working/base branch selection
    ↓
Read engineering rules; prepare complete plan and Constitution Check
    ↓
Create GitHub issue and verify its identity and full contents
    ↓
STOP — approval 1: implement the issue
    ↓
Retrieve the issue again; use the fresh specification and recheck rules
    ↓
Synchronize the selected base; create gh-<issue-number>
    ↓
Implement → validate → commit → record implementation checkpoint
    ↓
STOP — approval 2: publish the validated implementation
    ↓
Push approved source → create and verify PR → record PR checkpoint
    ↓
STOP — approval 3: merge the retained source revision
    ↓
Verify and merge PR through MCP → verify remote result → synchronize local base
    ↓
Record finalization checkpoint → separately close issue and verify closure
```

Earlier approval does not authorize a later gate. Scripts do not establish that
a human approved an action; the agent must enforce the pauses in `AGENTS.md`.
An explicit request to implement an existing issue may supply implementation
approval, but still requires retrieval of that exact issue and the later
publication and merge approvals.

### 1. Select the target and establish the specification

The user explicitly selects `OWNER`, `REPO`, and `WORKING_BRANCH`. Repository
discovery can help identify candidates but does not select one or authorize
repository creation. The working branch is mandatory: it is never inferred
from HEAD and never defaults to `main`. An explicitly selected `main` is valid.

The issue plan includes requested behavior, affected components, approach,
technical considerations, validation, a Constitution Check, and applicable
coding standards. Successful creation requires a verified issue identity and
targeted readback. The agent reports the actual reference and URL, then stops
for implementation approval.

After approval, the full freshly retrieved issue is authoritative. The user
may have edited it during the pause. An insufficient specification requires
clarification; remembered plans do not replace the retrieved contents.

### 2. Prepare the branch and implement

Branch preparation verifies a clean, attached worktree, writable Git metadata,
and effective origin fetch and push URLs matching the selected GitHub
repository. It synchronizes the exact local working branch with `pull --ff-only`
and creates `gh-<issue-number>`. Existing issue branches, divergent bases, and
identity mismatches stop preparation without resetting or overwriting history.

The implementation follows the approved issue, constitution, and coding
standards. Application source remains under `src/`; non-source changes outside
that directory must be part of the approved scope.

### 3. Validate, commit, and record implementation

The Python project validation required by `AGENTS.md` runs from the project root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Implementation-related failures must be resolved within scope before staging
and committing. Only issue-related files are staged. Commit messages use a
meaningful description and a non-closing canonical issue reference:

```text
Add configuration validation. owner/repository#42
```

This is a format example, not an actual issue identity. Automatic issue-closing
keywords are excluded from commits and PR text because closure occurs only
after verified finalization.

The agent captures the actual validated implementation commit, records a
successful implementation checkpoint on the issue, reports the results, and
stops for publication approval.

### 4. Publish and retain the review state

Publication verifies local identity, cleanliness, effective remotes, MCP
capabilities, and the approved source commit. It checks for an existing matching
PR, pushes the exact approved source, creates the PR, and verifies its returned
identity, head, and base. An existing matching PR is a recovery stop; it does
not authorize another creation or automatic resumption.

The successful publication JSON retains these exact fields:

```text
owner, repo, issue_number, issue_url, issue_reference,
PR_ID, PR_URL, SOURCE_COMMIT, BRANCH, WORKING_BRANCH
```

The whole result must survive the approval pause unchanged. After the PR
checkpoint succeeds, the agent reports the PR URL, source, base, and approved
commit, then stops for separate merge approval.

If the reviewer requests revisions, keep the PR open and stop the merge path
for an explicit recovery decision. The normal scripts do not implement a
revision and resubmission workflow. A revised source commit requires renewed
validation and approval of that source before publication or merge; never
overwrite retained approval state or rerun publication against an existing PR
to bypass recovery.

If the user instead decides to abandon the change, close the PR without merging
only on an explicit instruction. Closing it does not complete the workflow,
automatically delete the branch, or close the related issue as completed.

### 5. Merge the approved source and synchronize

The merge phase receives the exact successful publication file. It rechecks
local and remote identities, PR state, checks, reviews, and mergeability.
The merge request uses the retained `SOURCE_COMMIT` as `expectedHeadSha` and
`merge_method=merge`. The current implementation has no squash or rebase
fallback. Missing expected-head protection or blocked, pending, or unknown
mergeability stops the operation. The script checks all observed commit statuses
and check runs, including checks that repository policy does not mark required.
Failed, pending, unknown, or incomplete observations block the merge. Check runs
must finish with success, neutral, or skipped outcomes; the latest substantive
review from each reviewer must not request changes. An empty check-run list means
no check runs were observed; a combined pending status with zero status contexts
means no commit statuses were observed. GitHub remains authoritative for
server-side policy; empty observations do not prove policy approval.

After merging, the script independently verifies the PR and merge commit,
fetches the retained base, checks merge ancestry, and synchronizes the local
base by fast-forward only. Final checks require a clean worktree and equality
between local and fetched-base commits. A newer base commit is acceptable when
it contains the verified merge.

A successful remote merge with failed local synchronization is incomplete
finalization. Branch deletion, history resets, automatic rebases, and promotion
to another branch are outside this workflow.

### 6. Record finalization and close the issue

Only verified merge, synchronization, and final checks permit the finalization
checkpoint. Only a successful checkpoint permits the separate issue closure
operation. Completion requires a targeted readback confirming the exact issue
has `state=closed`.

## Skills

Read the relevant skill before invoking its entry points. Every required script
must exit successfully before dependent work proceeds.

| Skill | Operation and entry points |
| --- | --- |
| [list-repositories](.agents/skills/list-repositories/SKILL.md) | Discover candidates from an explicit query: `list-repositories.sh`. |
| [create-issue](.agents/skills/create-issue/SKILL.md) | Create and read back the full issue plan: `create-issue.sh`. |
| [get-issue](.agents/skills/get-issue/SKILL.md) | Retrieve the authoritative issue and validate identity: `get-issue.sh`. |
| [git-change-workflow](.agents/skills/git-change-workflow/SKILL.md) | Verify origin and prepare the explicitly based issue branch: `prepare-change-branch.sh`. |
| [update-issue](.agents/skills/update-issue/SKILL.md) | Record checkpoints and separately close/read back the issue: `comment-issue.sh`, `close-issue.sh`. |
| [finalize-implementation](.agents/skills/finalize-implementation/SKILL.md) | Publish or merge in separate approved phases: `publish-implementation.sh`, `merge-implementation.sh`. |

Bash entry points and shared libraries provide deterministic operations around
MCP requests and Git commands. They do not automatically advance the complete
lifecycle. Service operations have no GitHub CLI, direct REST/GraphQL, or
alternative-provider fallback.

## Configuration and authentication

Use [.agents/.env.example](.agents/.env.example) as the configuration reference.
Create the untracked `.agents/.env` locally from that example, preserving any
existing file, and configure credentials privately. The installer supplies the
example only. All skill invocations load this file through uv from the project
root:

```bash
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/get-issue/scripts/get-issue.sh \
        "$OWNER" "$REPO" "$ISSUE_NUMBER"
```

Bind the actual retained issue identity in the calling shell before running this
example. uv loads dotenv values for the child process; the Bash scripts do not
load files themselves. `--no-project` avoids synchronizing the application's
Python environment. Existing environment values take precedence over `.env`.
Do not source the file as shell code or print its contents. Use the prefix for
each skill invocation, including when an agent starts a fresh shell.

The explicit environment file must exist, including in new worktrees. If you
supply credentials externally, retain a local file containing only non-secret
settings. For local diagnostics with those values loaded, run
`uv run --no-project --env-file .agents/.env -- lean-sdd doctor .`.
Plain `lean-sdd doctor` continues to inspect only its inherited environment.

| Setting | Purpose |
| --- | --- |
| `GITHUB_MCP_URL` | Official MCP endpoint, configured as `https://api.githubcopilot.com/mcp/`. |
| `GITHUB_TOKEN` | Credential supplied privately in the untracked `.agents/.env`, through the environment, or by a secret manager. |
| `MCP_PROTOCOL_VERSION` | Protocol selection; the bundled template uses `2025-06-18`. |
| `MCP_TOOLSETS` | Optional toolset selection; an empty value uses endpoint defaults. |
| `MCP_CONNECT_TIMEOUT`, `MCP_TIMEOUT` | Transport connection and request limits. |

`OWNER`, `REPO`, and `WORKING_BRANCH` are explicit workflow selections passed to
the appropriate scripts. Bind these and retained issue/PR arguments in the
calling shell: it expands arguments before uv loads the environment file.
`.env` configures the command, not repository selection or workflow identity.

MCP authentication and Git authentication are separate. An MCP `get_me` response
establishes identity access, not issue-write permission, merge permission, or
Git push access. The user's SSH or HTTPS Git setup must independently support
the selected remote. Tokens must not be embedded in remote URLs or output logs.

Before live operations, use the read-only procedure in
[setup and readiness](.agents/README.md#environment-and-capability-verification)
to verify the deployed tool schemas, authenticated identity, and both publication
and merge capability contracts. Repeat phase checks after approval pauses as
specified by the skills.

Local `.agents/.env` files must remain untracked. The supplied `.gitignore`
ignores `.env` files and preserves `.env.example`; keep equivalent protection
when integrating the bundle into another repository. Do not copy existing local
credentials into a target project.

## Retained state and failure handling

GitHub issue numbers are repository-scoped. Keep `owner/repo#number` and the
returned URL together with the numeric issue number. A database issue ID, issue
number, and PR number are different identifiers; `gh-42` alone does not identify
a repository.

Keep successful JSON results in a private, durable directory outside the
worktree using `umask 077`. Parse them with jq; never source or evaluate them as
shell code. The source commit returned by branch preparation is the starting
revision, not the later validated implementation commit approved for publication.

A nonzero script exit is a failure even if some output or a transport response
looks successful. Stop dependent operations and preserve known effects and
uncertainty. Never guess an identity or automatically repeat uncertain issue,
comment, PR, merge, or closure writes.

When a required operation fails after a known issue exists and before closure
begins, record one factual failure checkpoint as specified in `AGENTS.md`.
If an audit comment itself fails, report it and stop without another audit
attempt. If closure fails or cannot be confirmed, report the observed state or
uncertainty without assuming the issue is open or closed.
Missing or mismatched approval state requires explicit recovery; new observations
must not silently replace the approved values.

## Adopting the workflow

1. Install Python 3.11 or newer, uv, Bash 4 or newer, Git, curl, jq, awk, grep,
   and mktemp. Install the CLI as described in [Install the CLI](#install-the-cli)
   and make `lean-sdd` and the required tools available on your PATH.
2. Start with an already provisioned GitHub repository and a usable local clone.
   Explicitly select its owner, repository, and existing working/base branch.
   Provisioning, remote replacement, and history migration are separate work.
3. Run `lean-sdd init` to install the governing documents and `.agents/`. Review
   existing project rules and reconcile conflicts explicitly; the installer
   refuses to overwrite an existing constitution or other differing files.
4. Provide application source under `src/`, project tests, dependency metadata,
   and the required validation tools. The workflow bundle does not create the
   application scaffold or its Python environment. Prepare that environment as
   described in [Python project management with uv](#python-project-management-with-uv).
5. Configure MCP credentials in the untracked `.agents/.env` and independent
   Git authentication. Commit the installed workflow files, installation record,
   and intended project setup through the repository's authorized setup process,
   keeping credentials untracked. Complete any required publication and review
   so the selected local base and its origin branch contain the setup and are
   synchronized before the first issue branch is prepared. Branch preparation
   requires a clean worktree, including untracked files, and rejects a local
   base that is ahead of or divergent from origin. The installer does not
   commit or publish this setup.
6. Verify the effective origin URLs, selected base, deployed MCP contracts, and
   identity through the documented setup procedure.
7. Perform an explicitly authorized acceptance run in a disposable project,
   observing all three real approval pauses and separate verified issue closure.
   Record actual results before claiming readiness.

Configuration is supplied through the documented interfaces. Repository identity
and base selection do not require hard-coding a repository into skill scripts.
Changes to the workflow itself must keep orchestration, engineering rules, and
operation contracts consistent.

### Adapting to another language

The main adaptation is in the project rules and validation environment:

- **`CONSTITUTION.md`:** update Python-specific wording and runtime support
  requirements. Review the mandatory `src/` boundary against the target
  language's layout; changing it requires an explicit constitutional amendment.
  Preserve the general correctness, security, verification, and reliability
  principles, and record approved amendments with their rationale and version.
- **`CODING_STANDARDS.md`:** replace Python idioms, typing, packaging, and tool
  requirements with the target language's conventions and quality standards.
- **`AGENTS.md`:** update language references and replace the application
  validation commands (`uv run pytest`, Ruff, and mypy) with the target project's
  build, test, lint, format, and applicable static-analysis commands. Preserve
  the `uv run --no-project --env-file .agents/.env -- bash` prefix used to invoke
  workflow skills. Keep engineering rules in the two rule documents and
  preserve the issue workflow, approval gates, and failure handling here.
- **Project configuration:** supply the target ecosystem's dependency manifests,
  lockfiles, build configuration, tests, and any CI checks. Review `.gitignore`
  for language-specific build outputs, caches, and local environment files.
  This bundle does not supply an application scaffold or CI configuration.
- **Supporting documentation:** update this README and `.agents/README.md` for
  the new setup and validation commands. Review validation references in the
  MCP, issue, and finalization contract documents linked below. Record validation
  and acceptance results for the adapted project.

`lean-sdd doctor` still checks for Python project metadata and `uv.lock`; editing
the workflow documents does not change these CLI checks. A non-Python project
without those files will receive warnings for their absence. Interpret those
warnings in the context of the chosen language and verify its dependencies and
toolchain separately. Continue to resolve applicable workflow and credential
configuration diagnostics; the CLI has no language-selection option.

The existing Bash skills and shared libraries handle Git and GitHub MCP
operations without running the application's Python checks, so changing the
application language does not normally require rewriting them. Their uv, Bash,
Git, curl, jq, and GitHub MCP prerequisites still apply; uv remains the
environment-file loader even for non-Python applications. Verify the adapted
validation commands and complete the acceptance workflow before claiming the
new configuration is ready.

## Developing and packaging the installer

From this repository root:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv build
```

The package exposes `lean-sdd` through the `lean_sdd.cli:main` entry point.
Hatchling's explicit file mappings in `pyproject.toml` bundle the authoritative
root documents and `.agents/` files as the `lean_sdd_templates` resource namespace.
The CLI reads those installed resources without requiring a source checkout.
The small files under `src/lean_sdd/template_overrides/` provide the installed
readiness checklist and local ignore rules. The build uses a file allowlist,
not a recursive copy of local `.agents/` state; update that list when adding a
workflow asset.

After editing template files, refresh the editable installation's bundled
resources with `uv sync --reinstall-package lean-sdd-cli` before testing.
The tests check conflicts, repeated initialization, symlink rejection, write
failure cleanup, diagnostics, links, Bash syntax, wheel contents, rebuilding a
wheel from the source archive, and isolated `uv tool install` execution. Build
tests use uv's local cache without network access after development setup.

`uv build` creates a wheel and source archive in `dist/`. This prepares release
artifacts locally; it does not publish a package. Public release still requires
selecting an available package name, establishing licensing and PyPI ownership,
and completing the relevant release review and live workflow acceptance.
Upgrading the CLI does not update previously initialized projects automatically.

## Validation and further reading

For an adopting Python project, run the four checks in
[Validate, commit, and record implementation](#3-validate-commit-and-record-implementation):
pytest, Ruff linting, Ruff formatting, and mypy through `uv run`. Add checks
required by the project's specification. The `uv build` command in the installer
development section packages Lean-SDD itself; adopting projects need a package
build only when their own requirements call for one. For Bash changes, include
syntax checks and relevant deterministic operational tests.

Offline checks cannot prove live permissions, server behavior, or real
human approval pauses. Live acceptance is side-effecting and requires explicit
authorization.

Detailed contracts:

- [Setup and readiness](.agents/README.md)
- [MCP transport and capability contract](.agents/github-mcp-contract.md)
- [Repository, issue, branch, and checkpoint contracts](.agents/github-issue-contract.md)
- [Publication, merge, and recovery contracts](.agents/skills/finalize-implementation/references/phase-contracts.md)


