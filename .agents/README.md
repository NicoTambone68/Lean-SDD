# Lean-SDD workflow setup

The complete orchestration is in [AGENTS.md](../AGENTS.md). Engineering rules
live in [CONSTITUTION.md](../CONSTITUTION.md) and
[CODING_STANDARDS.md](../CODING_STANDARDS.md). Read these before implementation.

## Layout and prerequisites

Paths are relative to the adopting project root. Six skills under `skills/`
provide Bash entry points; shared helpers live in `lib/`. Scripts perform
individual operations, while the agent owns sequencing and human approval.

The workflow requires Bash 4 or newer, Git, curl, jq, and standard shell tools
including awk, grep, and mktemp. On systems shipping older Bash, install a
compatible version and make it available as `bash`. Git uses separate SSH/HTTPS
credentials. Python projects require uv and their declared validation tools;
there is no independent Python environment for the Bash skills.

Supply an already provisioned GitHub repository and explicitly select its
owner/repository and existing working/base branch. Both effective origin fetch
and push URLs must identify that repository. No base defaults to `main`.
Provisioning, migration, and remote replacement are outside this workflow.

`lean-sdd doctor` performs local diagnostics without loading `.env`, contacting
GitHub, running project code, or proving readiness. A missing credential is
reported as a warning so installation can be inspected before credentials are
configured. Local warnings still need resolution where relevant to live use.

## Environment and capability verification

Scripts do not auto-load `.env` or connector configuration. Export reviewed
values in the caller's environment using [.env.example](.env.example) as a
reference. Supply `GITHUB_TOKEN` privately through a secret manager or an
interactive non-echoing read. Do not embed it in commands, remote URLs, or logs.

```bash
export GITHUB_MCP_URL='https://api.githubcopilot.com/mcp/'
read -r -s -p 'GitHub MCP token: ' GITHUB_TOKEN
export GITHUB_TOKEN
export MCP_PROTOCOL_VERSION='2025-06-18'
export MCP_TOOLSETS=''
```

Pass the actual selected `OWNER`, `REPO`, and `WORKING_BRANCH` explicitly to the
scripts. Configuration placeholders never replace user selection. Keep result
JSON in a private, durable directory outside the worktree; use `umask 077` and
parse JSON with jq, never source or evaluate it.

Before live operations, verify the deployed complete schemas, both phase
contracts, and identity through the actual Bash libraries. Set `AGENT_DIR` to
this project's absolute `.agents` path and `EVIDENCE_DIR` to an existing private
directory outside the worktree. The following performs MCP reads only:

```bash
set -euo pipefail
umask 077
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
```

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
