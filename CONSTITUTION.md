# Python Project Constitution

Version: 2.0.0
Ratified: 2026-08-17
Last amended: 2026-10-12

## Purpose and Authority

This constitution defines engineering invariants for general-purpose Python
projects. MUST and MUST NOT express requirements; SHOULD expresses a default
that may be departed from with a documented technical reason; MAY expresses an
option.

[CODING_STANDARDS.md](CODING_STANDARDS.md) defines the concrete Python coding,
testing, and tooling rules that implement these principles. Both documents
apply to implementation and review. Coding standards MUST NOT weaken this
constitution. Conflicts MUST be resolved before affected implementation proceeds.

[AGENTS.md](AGENTS.md) defines orchestration: task intake, approvals, issue and
branch handling, validation execution, and publication. It MUST reference and
enforce the engineering rules without silently overriding them. Workflow
procedures belong there, not in this constitution or the coding standards.

## I. Correctness Before Complexity

Implementations MUST favor the simplest design that correctly satisfies the
current specification. New abstractions, frameworks, dependencies, or layers
MUST NOT be introduced solely for hypothetical future requirements.

Optimization MUST follow demonstrated need or measurement and preserve
observable correctness. Existing project conventions SHOULD be preferred when
they remain compatible with the specification and these rules.

Rationale: Simplicity makes behavior easier to understand, verify, and maintain.

## II. Explicit Contracts and Data Integrity

Component inputs, outputs, state transitions, and failure behavior MUST have
clear contracts. External input MUST be validated at trust boundaries; type
annotations alone do not validate runtime data.

Representations MUST preserve the required precision, range, units, encoding,
and time semantics. Numerical types, rounding, tolerances, and conversions MUST
be chosen for the actual domain rather than imposed universally. Missing,
invalid, and empty values MUST remain distinguishable when their meanings differ.

Changes to stored data or public interfaces MUST address compatibility and
migration where applicable. Persistent state changes MUST preserve declared
invariants, including under partial failure.

Rationale: Correctness depends on preserving meaning across boundaries.

## III. Cohesive Design and Controlled Side Effects

Components SHOULD have clear responsibilities and explicit dependencies. Core
logic SHOULD be separable from filesystem, network, database, and user-interface
operations so it can be understood and tested independently.

Imports MUST NOT unexpectedly perform application work, access external
services, or mutate persistent state. Resource ownership and lifetime MUST be
clear. Concurrent work MUST define ownership of shared state and its
synchronization, cancellation, and shutdown behavior.

Project source MUST remain under `src/`. Tests, documentation, configuration,
and other non-source artifacts outside `src/` MAY change only within the
approved scope. Application behavior MUST NOT be moved into those artifacts
to evade the source boundary.

Rationale: Explicit boundaries limit coupling and make failures easier to isolate.

## IV. Evidence-Based Verification

Behavioral changes MUST have verification proportionate to their impact.
Tests MUST exercise observable behavior, boundary conditions, failure paths,
and relevant invariants rather than merely mirror implementation details.
Deterministic logic SHOULD be tested independently of slow or external systems.
Integration tests MUST cover interactions that isolated tests cannot establish.

Required tests and static checks MUST pass before a change is declared validated.
Tests, diagnostics, or quality thresholds MUST NOT be disabled or weakened to
conceal defects. Reports MUST distinguish checks that passed, failed, or were
not run; a passing check MUST NOT be claimed without execution evidence.

Rationale: Confidence comes from relevant evidence, not from complexity or test count.

## V. Reproducible Builds and Predictable Execution

Supported Python versions, dependencies, configuration requirements, and build
and validation commands MUST be declared. Dependency resolution MUST be
reproducible for development, validation, and deployed applications. Libraries
MUST declare appropriate compatibility ranges for consumers.

Results that depend on randomness, time, ordering, environment, or external data
MUST make those dependencies explicit when reproducibility matters. Tests MUST
control them where practical. Known nondeterminism MUST be documented rather
than hidden behind unsupported reproducibility claims.

Rationale: Maintainers must be able to recreate both working and failing behavior.

## VI. Security and Privacy by Design

Untrusted data MUST NOT be treated as executable code or trusted instructions.
Access to files, services, and credentials MUST use only the privileges needed
for the intended operation. Secrets MUST NOT be committed, embedded in code,
or exposed through logs, exceptions, or test artifacts.

Sensitive data collection, storage, and exposure MUST be limited to the
specified purpose. Dependencies and security-sensitive interfaces MUST be
assessed in proportion to their risk. Security controls MUST NOT be bypassed
merely to make development or testing convenient.

Rationale: Security and privacy are properties of correct software, not optional extras.

## VII. Explicit Failure and Operational Safety

Failures MUST be surfaced with useful context and MUST NOT be silently ignored
or converted into misleading success. Resources MUST be released on success,
failure, and cancellation.

External operations MUST have appropriate time and resource bounds. Retries
MUST be bounded and account for duplicate effects; uncertain outcomes MUST NOT
be treated as confirmed failures safe to repeat. Destructive or irreversible
behavior MUST have safeguards appropriate to its impact.

Diagnostics MUST support troubleshooting without disclosing sensitive data.
Experimental or test behavior MUST NOT implicitly activate production effects.

Rationale: Reliable systems remain understandable when dependencies fail.

## VIII. Maintainable and Compatible Interfaces

Code MUST communicate intent through clear names, appropriate type annotations,
and documentation of non-obvious behavior. Public interfaces MUST document
contracts and compatibility expectations where they affect consumers.

Breaking changes MUST be explicit and include migration guidance where needed.
Dependencies MUST have a justified purpose and be maintained within the project's
supported environment. Performance and resource consumption MUST be evaluated
against actual requirements when changes could materially affect them.

Rationale: Software must remain usable and changeable after its first implementation.

## Governance

### Constitution Check

Every implementation plan MUST include a Constitution Check covering each
principle with PASS, NOT APPLICABLE, or VIOLATION and a concise justification.
PASS means the proposed work is consistent with the principle; it is not a claim
that unexecuted validation has passed. NOT APPLICABLE requires an explanation.

A VIOLATION blocks affected implementation until the conflict is resolved or an
explicitly approved constitutional amendment changes the governing rule.
Implementation plans MUST also account for applicable coding standards.

### Amendments

Amendments require explicit user approval and a recorded rationale. The
constitution MUST NOT be modified merely to make an implementation easier.
Related coding standards and orchestration references MUST remain consistent
with an approved amendment.

### Versioning

Constitution versions follow semantic versioning:

- MAJOR: removal or incompatible redefinition of an existing principle.
- MINOR: addition of a principle or material extension of governance.
- PATCH: clarification that does not materially alter project constraints.

Every amendment MUST update the version and last-amended date.

### Amendment Record

- **2.0.0 — 2026-10-12:** Explicitly requested generalization for Python projects.
  Replaced domain-specific invariants with broadly applicable correctness,
  design, verification, reproducibility, security, reliability, and maintenance
  principles. Established the coding standards as the concrete rule companion
  and reserved orchestration for `AGENTS.md`.
