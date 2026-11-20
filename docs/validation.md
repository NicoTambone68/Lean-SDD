# Explicit reviewed validation

`lean-sdd validate [directory]` executes the complete current validation plan.
The directory defaults to the current directory. Invoking it is an explicit
execution request: first review the project rules, installed profiles, current
component mapping and all configured commands through the authorized workflow.
Parsing configuration, initializing a project, importing modules, or running
doctor never executes this runner or grants trust to project code. There is no
per-command approval flag or stored automatic-trust setting.

## Preparation before execution

The CLI requires a valid, bounded, regular installation record (schema 1 or 2).
Installed profiles must be available in the static catalog. An unavailable
historical profile never falls back to Python. A configured installation requires
its current `lean-sdd.toml`; invalid or absent configuration never defaults.
Historical records are not rewritten or compared to today's release hashes as a
condition of execution: reviewed local rules and template customization remain
user-owned. Use doctor separately to inspect original asset integrity.

For schema 2, each configured profile's standards file under `.agents/standards/`
must appear in the installation record and be a readable regular file at its
declared path. Missing entries, missing files, symbolic links, directories, and
read errors block the entire suite. Reviewed local edits are allowed. Schema 1
uses its historical Python layout.

The complete mapping/check schema is validated before any process launches:
mandatory categories, required status, exact Python argv, the TypeScript npm-run
adapter, scope, profile membership,
normalized contained paths, and finite positive timeouts. Every component and
check directory must exist, and symlink/non-directory boundaries are rejected.
Each Python component requires a regular, readable, UTF-8 `pyproject.toml` of at
most 1 MiB with a `[project]` table, plus a regular `uv.lock`. Presence is not a
claim of complete package-metadata validity or lock freshness; those remain the
responsibility of the actual tools. Missing application files block validation
even though doctor allows their absence as adoption-time warnings.

TypeScript requires all three bounded metadata files (package.json,
package-lock.json and tsconfig.json) and compatible declarations. Every missing,
invalid or unsupported TypeScript observation blocks execution. The profile's
contract is installed at `.agents/docs/typescript.md`. Metadata checks never
execute compiler/configuration modules or install dependencies.

Each executable is located before execution using the invocation's PATH. Relative
executable paths and relative/empty PATH entries resolve against that check's
working directory, not the caller's original directory. A missing required
executable blocks all execution, including runnable optional checks. An optional
missing executable is reported but does not prevent the required suite.

Execution is supported only on Linux, from the main Python thread. Unsupported
platforms or threading contexts fail preparation without launching commands.
This is an explicit initial support boundary; Windows/macOS process cleanup has
not been implemented or claimed. The documented Bash-based workflow can run
inside an appropriate Linux environment such as WSL.

## Commands and order

All configured checks run in ascending check-name order, irrespective of the
order of TOML declarations. No dependency filtering, parallel scheduling, early
exit on ordinary failure, or automatic retries occur. Python's mandatory commands
are unchanged and run from each selected Python component's root:

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Python mandatory commands cannot be replaced. TypeScript requires types, lint,
format, tests and build, each using exactly npm run with one reviewed script name
at the component root. Default scripts are typecheck, lint, format:check, test and
build; generated check names sort build first. Existing script names may be
selected explicitly. Neither profile's mandatory categories can be marked optional,
or satisfied by a project-wide check. All required project-wide integration
checks are additional obligations. Optional checks remain visible and do not
satisfy mandatory categories.

Legacy Python mode without TOML resolves the equivalent root component and four
required checks, each with a 300-second timeout. Their names sort as
`python-format`, `python-lint`, `python-tests`, `python-types`. Default generated
Python configuration uses that same plan. An explicit mapping may use different
check names, so its alphabetical order can differ.

The plan snapshots configuration and environment at invocation. Directories,
installed standards files, and required profile metadata are checked again
immediately before each launch. A changed boundary or required-file precondition
stops execution and leaves remaining checks not run. The runner never reloads
changed command definitions to execute new instructions mid-suite.
Avoid concurrent project/PATH changes; these checks
are not protection against a hostile process racing filesystem operations.

## Results and exit status

Each result identifies check name, component/profile or project scope, and whether
it is required. A naturally observed return code is preserved, including negative
signal return codes. States have distinct meanings:

| State | Meaning |
| --- | --- |
| `passed` | The command exited zero; this does not establish the entire suite passed. |
| `failed` | The command exited nonzero or was killed by a signal independently of runner cancellation. |
| `missing-executable` | Preflight could not find it, or it/its interpreter disappeared before launch. |
| `timed-out` | The configured execution deadline expired; the owned group was terminated. |
| `cancelled` | The active check was interrupted by SIGINT/SIGTERM or KeyboardInterrupt. |
| `not-run` | No process was launched for this check because preparation, cancellation, or infrastructure failure stopped the suite. |
| `error` | The command could not be launched or monitored; raw exception details are not printed. |

Ordinary nonzero exits, timeouts, and individual launch errors allow later runnable
checks to continue. Monitor errors, uncertain cleanup, and changed preparation
boundaries stop the invocation. Missing executables discovered during preflight
retain their explicit state even when other checks cannot start. If configuration
cannot be parsed at all, there is no trustworthy check list: report the preparation
error rather than inventing check identities or results.

Exit 0 requires every required check to pass, no preparation/infrastructure error,
and no cancellation. Optional failures alone do not cause exit 1. Any required
unsuccessful/unrun check, preparation failure, or infrastructure/cleanup uncertainty
returns 1. CLI usage errors return 2. Cancellation returns 130 for SIGINT and 143
for SIGTERM. A check's own signal exit is a check failure, not runner cancellation.
Signal handlers are restored when the invocation ends.

## Process lifetime and cleanup

Each check starts a new Linux session/process group. Its configured timeout starts
when the child has been created; executable resolution and preparation precede
that deadline. The runner uses a monotonic clock and polls at most every 50 ms.
A blocking OS process-creation call itself is outside the timed child lifetime.

On timeout, interruption, monitor error, or ordinary parent completion with
background descendants still present, the runner sends SIGTERM to the entire
owned group. It gives members a 0.5-second grace period, then sends SIGKILL to any
remaining group. It waits up to 1 second to reap its direct child. Cancellation
signals received during cleanup are recorded without interrupting cleanup;
remaining configured checks are not launched. Cleanup uncertainty is an explicit
failure and stops further execution rather than claiming success.

Children and grandchildren that remain in the group receive these signals, even
if their direct parent has exited. Tests use real descendants that ignore SIGTERM
to verify escalation and termination. The runner reaps its own child; the OS parent
of an orphan owns its final reaping, so terminated orphan zombies may briefly
remain visible. This is not an OS sandbox: reviewed commands must not detach via
`setsid`, change process groups, or delegate work to unrelated services. Such
escaped work is outside the owned group and cannot be guaranteed cleaned up.
Uninterruptible kernel work and external side effects also cannot be rolled back.
Do not select checks requiring these unsupported lifecycle behaviors.

## Output, trust and credentials

Commands receive argv as structured arguments with `shell=False`, an explicit
working directory, and a snapshot of the inherited environment. No shell expands
metacharacters in individual arguments. An explicitly configured interpreter or
shell command still executes code and must be reviewed accordingly. The runner
does not source `.env`; callers are responsible for any environment they supply.

Standard input is closed via the null device. Child stdout and stderr stream
directly to the invoking process's output streams: no runner pipe buffering,
output accumulation, or persistent log file is created. Summaries follow the suite
and omit raw argv, environment values and exception output. Command output itself
is unredacted and may contain sensitive data; review what commands print, avoid
secrets in argv/configuration, remove unnecessary credential variables, and control
where terminal output is redirected. There is no automatic secret-redaction claim.

Validation executes project code with the user's access. It can modify files,
install/synchronize dependencies (including `uv run`'s normal behavior), or use
network and credential access available to the command. The runner neither adds
such actions independently nor confines them. Dry inspection belongs to doctor;
validation should only be invoked after the required review.

The Python APIs are `prepare_validation(...) -> ValidationPlan`,
`run_validation(plan) -> ValidationResult`, and the CLI-oriented `validate(target)`.
Only pass plans produced by the preparation API to the runner. Its registry and
environment arguments are explicit in-process test/integration adapters, not
configuration-driven plugins. Results retain typed check identities; callers must
not dump configuration or credential-bearing fields into audit logs.
