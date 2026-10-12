# Lean-SDD workflow setup

The complete orchestration is in [AGENTS.md](../AGENTS.md). Engineering rules
live in [CONSTITUTION.md](../CONSTITUTION.md) and
[CODING_STANDARDS.md](../CODING_STANDARDS.md). Read these before implementation.

## Layout and prerequisites

Paths are relative to the adopting project root. Six skills under `skills/`
provide Bash entry points; shared helpers live in `lib/`. Scripts perform
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

The adopting Python project supplies its own source, tests, `pyproject.toml`,
and `uv.lock`. Required commands are defined in `AGENTS.md`: pytest, Ruff linting
and formatting, and mypy through `uv run`. The installer does not create an
application scaffold or execute those commands in the target project.

Live acceptance remains separate from installer tests and local diagnostics.
See [readiness and acceptance](github-workflow-acceptance.md). Historical server
observations in the reference contracts do not prove current capabilities or
permissions. Use current observations for each deployment.

Operational references:

- [MCP transport contract](github-mcp-contract.md)
- [Issue and branch contract](github-issue-contract.md)
- [Publication and merge contracts](skills/finalize-implementation/references/phase-contracts.md)
