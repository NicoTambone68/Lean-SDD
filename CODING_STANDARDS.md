# Python Coding Standards

These standards implement the principles in
[CONSTITUTION.md](CONSTITUTION.md). Its requirement vocabulary and authority
apply here. [AGENTS.md](AGENTS.md) owns workflow sequencing, approvals, and the
execution of validation; this document defines code quality requirements.

## 1. Readability and Design

- Follow PEP 8 and the project's configured formatter and lint rules.
- Prefer explicit, straightforward code and established project patterns.
- Use descriptive names; avoid unexplained abbreviations and magic values.
- Keep functions and modules focused. Split logic when it improves clarity,
  rather than to meet an arbitrary size threshold.
- Prefer composition to unnecessary inheritance, and functions or simple data
  structures to classes without a meaningful responsibility.
- Avoid speculative abstractions and dependencies. Prefer the standard library
  when it adequately satisfies the requirement.

## 2. Types and Interfaces

- New functions and methods MUST annotate parameters and return values,
  including `-> None` where appropriate; implicit `self` and `cls` need no
  annotation. Public attributes MUST be annotated unless their types are
  unambiguously inferred by the configured type checker.
- Prefer precise types, including explicit optional values. Use protocols,
  typed mappings, dataclasses, or other structured types when they clarify a
  real contract; avoid introducing them mechanically.
- Prefer abstract collection types for inputs when concrete mutability or
  implementation details are not required.
- Avoid `Any`. Necessary dynamically typed boundaries MUST remain narrow.
- Casts and type-checker suppressions MUST have a specific justification and
  MUST NOT substitute for runtime validation of external data.
- Public interfaces MUST define relevant input constraints, return semantics,
  exceptions, and compatibility expectations.

## 3. Documentation

- Public modules, classes, and callables SHOULD use Google-style docstrings
  where documentation is useful.
- Document behavior, units, constraints, side effects, and non-obvious failure
  modes rather than restating names or type annotations.
- Comments SHOULD explain intent and tradeoffs. Avoid comments that duplicate
  straightforward code.
- Changes MUST update affected user documentation, configuration examples,
  and interface descriptions. Breaking changes MUST identify required migration.
- Examples MUST avoid real credentials and unsupported success claims.

## 4. Data and Numerical Semantics

- Validate external values before using them in domain logic. Distinguish
  parsing errors from valid empty or absent values when the contract requires it.
- Choose integers, floats, `decimal.Decimal`, or other representations according
  to precision and range requirements; no single numeric type is mandatory for
  every domain. Make rounding, units, and conversions explicit.
- Floating-point comparisons MUST use tolerances appropriate to the domain
  when exact equality is not meaningful. Handle non-finite values when relevant.
- Timestamps representing instants SHOULD be timezone-aware. Define timezone,
  daylight-saving, and serialization behavior where those affect correctness;
  use monotonic clocks for elapsed-time measurement.
- Text file and interchange formats MUST use an explicit encoding where the
  platform default could change behavior.
- Persistent schema changes MUST consider existing data, migration failures,
  and compatibility with supported consumers.

## 5. Errors and Resource Management

- Raise meaningful exceptions when required preconditions or invariants fail.
  Do not use `assert` to validate runtime inputs or enforce security controls.
- Catch specific exceptions where the code can recover or add useful context.
  Preserve exception causes when translating errors.
- Broad exception handlers require a documented purpose, such as an application
  boundary; they MUST NOT silently discard failures.
- Use context managers or reliable `finally` cleanup for files, locks,
  connections, and other owned resources.
- Configure timeouts for external calls and bound retries. Retry only when
  repeated effects are safe or protected by an explicit idempotency mechanism.
- Use transactions or atomic replacement when needed to prevent partially
  written persistent state; define recovery behavior for failures.

## 6. Python Runtime Practices

- Use `pathlib` for filesystem paths where practical.
- Avoid mutable default arguments, hidden global mutable state, and wildcard
  imports. Keep comprehensions and expressions immediately readable.
- Module imports MUST avoid application execution and external side effects.
  Command entry points SHOULD call an explicit main function and use a
  `__name__ == "__main__"` guard when directly executable.
- Configuration MUST be explicit, validated, and distinct from core logic.
  Avoid reading environment variables throughout unrelated business code.
- Inject clocks, random generators, and external clients where doing so makes
  behavior meaningfully controllable and testable.
- Do not block an asynchronous event loop with synchronous I/O or expensive
  computation. Concurrent tasks MUST have explicit ownership, bounded work,
  cleanup, and cancellation handling; cancellation MUST NOT be swallowed.
- Synchronize shared mutable state or avoid sharing it. Do not assume the
  interpreter makes compound operations or application invariants atomic.

## 7. Security and Diagnostics

- Never commit secrets or put them in command arguments, logs, tracebacks,
  fixtures, or generated artifacts. Use the project's credential mechanism.
- Use parameterized database queries and structured subprocess arguments.
  Avoid shell interpolation of external input, dynamic evaluation, and unsafe
  deserialization of untrusted content.
- Validate externally supplied paths and destinations against the intended
  access boundary; account for traversal and links where relevant.
- Preserve transport certificate verification and use least-privilege access.
- Use module loggers for library diagnostics; applications own logging
  configuration. CLI output MAY use standard output for its intended results.
- Diagnostics SHOULD include actionable context while excluding secrets and
  unnecessary personal or sensitive data.

## 8. Testing

- Use `pytest`. New or changed behavior MUST have appropriate tests where
  practical; omissions require a recorded reason and alternative verification.
- Bug fixes SHOULD include a regression test reproducing the defect.
- Test observable contracts, boundary cases, failure handling, and invariants.
  Avoid tests that merely duplicate implementation logic.
- Prefer fast, deterministic unit tests for isolated logic. Add integration
  tests for relevant database, filesystem, network, or component contracts.
- Tests MUST NOT depend on execution order, uncontrolled randomness, wall-clock
  timing, or undeclared access to live services and credentials.
- Use temporary directories and scoped fixtures; clean up created resources.
  Parameterize cases when it improves clarity.
- Prefer real local components or small fakes over excessive mocking. Test
  doubles MUST preserve relevant contracts, including error behavior.
- Control time and randomness explicitly when they affect results. Property
  tests MAY supplement example tests for broad invariants.
- Slow or external-service tests MUST declare their requirements and remain
  distinguishable from the normal deterministic suite. Expensive end-to-end
  runs MUST NOT replace focused checks for deterministic defects.

## 9. Packaging, Dependencies, and Compatibility

- Declare supported Python versions, direct runtime dependencies, development
  dependencies, and tool configuration in `pyproject.toml` where supported.
- Maintain the project's lockfile for reproducible development and application
  deployment. Library metadata MUST express supported dependency ranges rather
  than depend on consumers using the development lockfile.
- Source packages belong under `src/`, as required by the constitution. Imports
  MUST work through the intended package installation; do not patch `sys.path`
  to conceal packaging defects.
- New dependencies MUST have a concrete purpose and compatible licensing,
  Python support, and maintenance characteristics.
- Dependency updates MUST preserve supported interfaces or explicitly document
  the required migration. Remove unused dependencies when within task scope.

## 10. Static Quality and Performance

- Code MUST satisfy the project's configured Ruff linting, Ruff formatting,
  and mypy type checks, as well as applicable tests. `AGENTS.md` specifies the
  validation commands and when they run.
- Diagnostic suppressions MUST be narrow and justified. Do not weaken shared
  configuration or remove tests to conceal implementation failures.
- Performance changes SHOULD be supported by representative measurements.
  Check correctness alongside speed, memory use, and other relevant limits.
- Unbounded input, buffering, recursion, or task creation MUST be constrained
  where it could violate the application's resource requirements.
