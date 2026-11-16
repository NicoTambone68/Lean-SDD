# Shared Coding Standards

These standards implement [CONSTITUTION.md](CONSTITUTION.md) for every declared
component. [AGENTS.md](AGENTS.md) owns workflow sequencing, approval gates,
validation execution, failure handling, and completion. Neither these standards
nor a language profile may weaken either document.

## Load all applicable language standards

Before planning or modifying files, read the constitution, root workflow, these
shared standards, and every installed language standard relevant to the change.
Do not rely on automatic discovery of nested instruction files. For a component
using several profiles, all their requirements apply. For shared-file changes,
identify all affected components and interfaces before deciding which standards
and verification are relevant.

Installed profile standards:

{{profile_standards}}

Treat profile requirements as cumulative. A profile cannot replace shared
governance or remove another applicable profile's mandatory checks. Report
contradictory requirements before implementation; do not silently choose a weaker
rule. Selecting a profile does not authorize executing its tools.

## Common engineering requirements

- Prefer the simplest correct design and explicit component contracts. Introduce
  abstractions or dependencies only for demonstrated requirements.
- Keep application source beneath repository root `src/`. Scope tests,
  documentation, configuration, and non-executable schemas explicitly. Component
  roots and component-local source roots must respect the constitution.
- Validate external input at trust boundaries. Preserve data meaning, precision,
  encoding, and time semantics; document compatibility and migration obligations.
- Keep core logic separate from external operations. Imports must not perform
  application work, contact services, or mutate persistent state.
- Make resource ownership, failure behavior, cancellation, and cleanup explicit.
  Bound external operations and retries, accounting for uncertain duplicate effects.
- Protect credentials and sensitive data. Do not evaluate untrusted metadata or
  command text. Review project commands before explicitly executing them.
- Verify observable behavior, boundaries, failures, and relevant invariants.
  Include integration or contract checks where isolated tests are insufficient.
  Never weaken diagnostics or tests to conceal failures.
- Declare supported environments, dependencies, configuration, and validation
  commands. Preserve reproducible dependency resolution and deterministic tests.
- Document public interfaces and non-obvious behavior, update affected examples,
  and communicate breaking changes with migration guidance.

## Validation and compatibility

The root workflow and each applicable profile define the required validation.
All required checks must pass before reporting validation success. Distinguish
passed, failed, and not-run checks; document any additional integration needs.
After reviewing the mapping and commands, the composed application workflow runs
`lean-sdd validate .` from the repository root on Linux. It runs every required
component and project check, including applicable interface tests. Python retains
its four mandatory commands at each component root. Focused checks do not replace
the final suite. Initialization and doctor never execute these commands; a doctor
setup warning may still block validation. See [setup](.agents/README.md#validation-and-readiness)
for command trust, prerequisites, and the separate repository maintenance gate.

Existing Python conventions, typing, documentation, numerical semantics, error
handling, runtime practices, security, tests, packaging, and static checks remain
fully applicable through the Python standards. Their normative text is preserved;
this common layer is not a replacement or a shortened Python policy.
