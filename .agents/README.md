# Lean-SDD workflow setup

The complete orchestration is in [AGENTS.md](../AGENTS.md). Engineering rules
live in [CONSTITUTION.md](../CONSTITUTION.md) and
[CODING_STANDARDS.md](../CODING_STANDARDS.md). Read these and every applicable profile standard before implementation. Root
coding standards explicitly link installed language standards; component and
shared-interface scope determines which rules apply. Six core skills are always
required; a supported profile may declare additional skills without overriding them.

## Layout and prerequisites

Paths are relative to the adopting project root. Six core skills under
`.agents/skills/` provide Bash entry points. Shared helpers live in
`.agents/lib/`. Scripts perform
individual operations, while the agent owns sequencing and human approval.

The workflow requires uv, Bash 4 or newer, Git, curl, jq, and standard shell tools
including awk, grep, and mktemp. On systems shipping older Bash, install a
compatible version and make it available as `bash`. Git uses separate SSH/HTTPS
credentials. uv loads the local environment file for skill invocations, even
when the application uses another language. Python projects also supply their
declared validation tools; the Bash skills have no Python package dependencies.

Supply an already provisioned GitHub repository and explicitly select its
owner/repository and existing working/base branch. Both effective origin fetch
and push URLs must identify that repository. No base defaults to `main`.
Provisioning, migration, and remote replacement are outside this workflow.

`lean-sdd doctor` performs local diagnostics without loading `.env`, contacting
GitHub, running project code, or proving readiness. A missing credential is
reported as a warning so installation can be inspected before credentials are
configured. Local warnings still need resolution where relevant to live use.

## Installation diagnostics

`.agents/lean-sdd-install.json` records the original template release and each
installed file's SHA-256 hash. Commit it with the workflow and preserve it when
customizing templates. Schema-version-1 records remain readable as legacy Python without rewriting them.
New installations use schema 2 with a sorted installed profile set and explicit
configuration mode; older CLIs need not understand schema 2. `lean-sdd.toml` owns
the current reviewed mapping and commands; the record owns original asset hashes.
A generated TOML is hashed, while pre-existing user TOML is preserved and unowned.
Valid edits within the installed profile set do not rewrite original hashes.
A missing configured TOML fails instead of inventing a replacement mapping. The installed template version can differ from the current CLI
version: updating the CLI never updates project templates automatically.

Run `lean-sdd doctor /path/to/project` to inspect three separate observations:

- Record validity: malformed JSON, invalid fields or hashes, unsupported schemas,
  and unsafe paths produce `FAIL`. Symbolic links are rejected.
- Installed-file integrity: matching the recorded original hash produces `PASS`;
  a different hash produces `WARN: Locally modified template`. Missing,
  unreadable, or non-regular recorded files produce `FAIL`.
- Release compatibility: matching versions and manifests produce `PASS`.
  Different versions produce `WARN`, including both versions. Identical template
  contents need no upgrade; changed contents produce an upgrade advisory listing
  added templates, removed templates, and changed reference hashes. The same
  version with a contradictory manifest produces `FAIL` with conflicting entries.

New templates absent from an older installation are upgrade advisories, not
missing-file failures. Templates removed from the current release are still
validated against their recorded original hashes. A version warning alone does
not mean corruption or require immediate migration. Review local modifications
and release differences separately; compare with a fresh installation in another
directory if needed. Do not edit the record to silence diagnostics.

Diagnostics never rewrite records or templates, repair files, or automatically
upgrade or downgrade an installation. They do not execute installed scripts or
load project credentials. Exit status is 0 when there are no failures, including
when warnings are present; 1 indicates an operational failure and 2 invalid CLI
syntax. Local diagnostics do not establish GitHub readiness.

## Environment and capability verification

Prepare an untracked `.agents/.env` from [.env.example](.env.example) without
overwriting an existing file. Add `GITHUB_TOKEN` privately, or provide it through
your environment/secret manager. The installer never creates or copies secrets.
In a new worktree, provision this local file separately; untracked files do not
arrive with a checkout. Keep it even when all settings are supplied externally,
because the explicit `--env-file` path must exist.

Invoke every skill from the project root with:

```bash
uv run --no-project --env-file .agents/.env -- \
    bash .agents/skills/get-issue/scripts/get-issue.sh \
        "$OWNER" "$REPO" "$ISSUE_NUMBER"
```

This example requires the actual retained issue identity, bound in the calling
shell. uv loads dotenv data into the child process without executing it as shell
code. The Bash scripts themselves do not auto-load configuration. `--no-project`
prevents application project discovery/synchronization for these Bash commands.
Existing environment variables take precedence over matching `.env` entries;
remove a stale exported value explicitly if you intend to use the file's value.
Do not source `.env`, print it, enable shell tracing, or place tokens in arguments.

The calling shell expands `"$OWNER"`, paths, and other arguments **before** uv
loads `.env`. Keep repository/base selection and retained issue/PR state out of
that file and bind them explicitly before invocation. Loading secrets for one
command does not export them into subsequent Codex shell commands; use the
prefix on every invocation. A uv failure stops dependent work without bypassing
the loader or retrying a write.

Store result JSON in a private, durable directory outside the worktree; use
`umask 077` and parse JSON with jq, never source or evaluate it.

Before live operations, verify the deployed complete schemas, both phase
contracts, and identity through the actual Bash libraries. Bind `AGENT_DIR` to
this project's absolute `.agents` path and `EVIDENCE_DIR` to an existing private
directory outside the worktree in the calling shell. This example performs MCP
reads only and passes those paths as data into a single uv-managed Bash process:

```bash
uv run --no-project --env-file .agents/.env -- \
    bash -s -- "$AGENT_DIR" "$EVIDENCE_DIR" <<'BASH'
set -euo pipefail
umask 077
AGENT_DIR=$1
EVIDENCE_DIR=$2
source "$AGENT_DIR/lib/github-mcp.sh"
source "$AGENT_DIR/lib/github-pr.sh"
mcp_connect "$GITHUB_MCP_URL" "$GITHUB_TOKEN" > "$EVIDENCE_DIR/initialize.json"
mcp_list_tools > "$EVIDENCE_DIR/tools.json"
github_mcp_check_capabilities "$EVIDENCE_DIR/tools.json"
c_phase=publication
c_capabilities "$EVIDENCE_DIR/tools.json"
c_phase=merge
c_capabilities "$EVIDENCE_DIR/tools.json"
mcp_call get_me '{}' > "$EVIDENCE_DIR/identity.json"
BASH
```

To check the loaded configuration locally without printing values or contacting
GitHub, use the installed CLI through the same loader:

```bash
uv run --no-project --env-file .agents/.env -- lean-sdd doctor .
```

Plain `lean-sdd doctor` still inspects only its inherited environment; it does
not parse `.env` itself. Neither form proves credential validity or permission.

The foundation and phase checks require the actual tools and fields consumed by
the scripts, including `expectedHeadSha` protection and merge-commit support.
Unsupported capabilities stop dependent work without a direct API or CLI
fallback. Identity access alone does not establish write, merge, or Git push
permission. Do not publish personal identity or session evidence.

## Using the workflow

Read the corresponding `SKILL.md` before each operation and require exit 0 before
advancing. `AGENTS.md` defines three distinct approval gates:

1. Create and verify the full issue; stop for implementation approval. Retrieve
   it again after approval, recheck the engineering rules, and prepare its branch.
2. Implement, validate, commit, and record the implementation checkpoint; stop
   for publication approval.
3. Publish and verify the PR, retain the complete successful JSON result, and
   record the PR checkpoint; stop for separate merge approval.
4. Merge only the retained approved source, verify remote results and local base
   synchronization, record finalization, then separately close/read back the issue.

A failed operation stops dependent work. Preserve known remote effects and
uncertainty, following the failure checkpoint rules in `AGENTS.md`. Do not
blindly retry uncertain writes or substitute new observations for approved state.

## Validation and readiness

For composed installations, review `lean-sdd.toml` and all applicable standards,
then explicitly run `lean-sdd validate .` from the root. Review every command and
working directory, including configuration edits, before execution. The CLI runs
structured argv without a shell, in deterministic check-name order; it does not
sandbox project code, redact child stdout/stderr, or make arbitrary commands safe.
Do not use the GitHub `.env` loader for application validation. Child processes
inherit your environment and normal tools may synchronize dependencies or access
the network. No automatic retry or automatic command approval is supplied.

Each Python component supplies its own source, tests, `pyproject.toml`, `uv.lock`,
and declared development tools. The full gate runs pytest, Ruff lint/format and
mypy through uv at each Python component root, plus all required project checks.
Optional failures remain visible; required nonzero exits, missing tools/setup,
timeouts, cancellation and not-run required checks prevent success. Doctor is
local and non-executing: missing application setup can be advisory there but
blocks validation. Init neither scaffolds applications nor executes checks.

Validation currently requires Linux process-group semantics, including Linux
under WSL, and invocation from the main thread. It terminates owned process groups
on completion, timeout and interruption; commands must not detach into new groups
or services. Native Windows and macOS validation are unsupported. Installation
and local diagnostics do not establish support for the complete Bash/Git workflow.

This Lean-SDD source repository and legacy Python installations retain the four
root maintenance commands in `AGENTS.md`. Component-aware applications use the
reviewed configured gate; additional profiles never remove mandatory checks.
For complete schemas, examples, diagnostics and execution behavior, read the
[configuration](../docs/configuration.md), [profiles](../docs/profiles.md),
[diagnostics](../docs/diagnostics.md) and [validation](../docs/validation.md) references.

Updating the CLI does not change installed documents. Use a separate fresh target
to compare releases, preserve the original record and local customizations, and
obtain a separately scoped manual migration plan before adopting new assets or
profile identities. Never edit hashes or rerun init to force an upgrade. New
releases may change template bytes; same-release repeats remain conservative.

Before claiming workflow readiness, obtain explicit authorization for a live run in a disposable project.
Verify current MCP capabilities and Git access for the selected repository and base.
Follow [the issue workflow](../AGENTS.md) through all three approval pauses, merge,
local synchronization, and verified issue closure. Record the observed results.

Operational references:

- [MCP transport contract](github-mcp-contract.md)
- [Issue and branch contract](github-issue-contract.md)
- [Publication and merge contracts](skills/finalize-implementation/references/phase-contracts.md)
