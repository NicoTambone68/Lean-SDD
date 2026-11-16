# TypeScript Coding Standards

These rules supplement [shared standards](../../CODING_STANDARDS.md), the
[constitution](../../CONSTITUTION.md) and [root workflow](../../AGENTS.md).
Read all applicable profiles for a component and every affected shared interface.
Conflicting standards block implementation. No profile replaces shared rules or
removes another profile's checks. See the [toolchain contract](../docs/typescript.md).

## Contracts and types

Use strict TypeScript compiler checking without disabling individual strict
checks. Prefer precise types, discriminated unions and explicit return contracts.
Treat untrusted input as unknown until validated at runtime; static types do not
validate network messages, JSON, environment values or database records.

Avoid any, non-null assertions, unchecked assertions and suppression comments.
An unavoidable escape requires a narrow scope, a documented reason and tests for
its safety assumptions. Never use an escape to hide a known contract mismatch.
Preserve precision and encoding; represent values outside safe integer range
explicitly and validate before conversion. Document JSON/date/unit semantics.

## Modules, execution and errors

Match Node ESM/CommonJS semantics to the declared package type and compiler
settings. Declare exports and public types deliberately; test consumer imports
and declaration output for libraries. Do not assume browser globals, UI
frameworks or bundler rewrites. Follow environment-appropriate extension rules.

Await promises or explicitly handle their rejection and lifetime. Do not discard
errors or detach work without owned cancellation/cleanup. Catch unknown errors
only where the program can recover or add safe context. Keep imports free of
application side effects; separate entry points from reusable logic. Bound I/O,
concurrency, timeouts and buffering. Clean up resources on failure/interruption.

Use parameterized interfaces and structured subprocess arguments. Never evaluate
untrusted data, expose credentials in output, or put secrets in package scripts.
Validate paths, authorization and external data at their trust boundaries.

## Layout and reproducibility

Application, executable configuration, runtime contract and generated application
code remain under repository root src as required by the constitution. A root
component uses src; a component beneath src may have its own source directory.
Scope tests, non-executable schemas, manifests and documentation separately.

Preserve conforming package manifests, manager choices, locks and compiler
configuration. Diagnose unsupported setups; never silently replace them. Commit
reviewed dependency locks and declare supported runtime/tool versions. Avoid
unnecessary dependencies; assess purpose, maintenance, licensing and compatibility.
Installation of workflow assets never authorizes installation or execution of
application dependencies. Do not run commands merely because metadata parses.

## Required verification

The five required categories are types, lint, format, tests and build. Run all
through explicitly reviewed npm scripts from each component root. Lint should
include type-aware promise and unsafe-operation rules; formatting must check
without rewriting at the validation gate. Compiler success alone is not evidence
of correct behavior, test coverage, runtime input safety or cross-language
compatibility. This initial profile targets compiled Node projects, so build and
declaration verification are required for every selected component.

Use deterministic behavioral tests, boundary/failure tests and relevant process
or filesystem integrations. Test Node ESM/CommonJS consumers where supported.
Interacting components require API/message compatibility tests, including runtime
validation on both sides; isolated Python/TypeScript type checks are insufficient.
Keep optional outcomes visible and never omit or downgrade required categories.
The root workflow owns execution, approvals, failure audits and completion.
