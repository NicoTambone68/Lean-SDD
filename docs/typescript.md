# TypeScript: Node/npm contract

TypeScript is a bundled production profile starting with CLI/template release
0.3.0. `lean-sdd languages` lists Python and TypeScript; the default remains Python.
The profile adds standards and validation configuration, preserving application
manifests, lockfiles and source. It installs no application or toolchain.

## Supported environment and acceptance

The agreed initial target is Linux (including Linux under WSL), Node 26 LTS,
npm and package-lock.json, for services, workers, CLI tools and libraries.
Node ESM and CommonJS are both covered. No browser, framework, bundler, npm
workspace, pnpm/Yarn, Bun/Deno or native Windows/macOS execution is advertised.

Pinned acceptance baseline: Node 26.13.1 and its bundled npm 11.20.0; TypeScript
6.0.3; ESLint 10.14.0; typescript-eslint 8.72.2; Prettier 3.10.0. These versions
passed real compiler, lint, formatting, test and build acceptance on Linux on
2026-11-16. npm generated the committed v3 fixture lock; `npm ci --ignore-scripts`
reproduced its exact dependencies in temporary projects.
The lint integration's documented TypeScript range is below 6.1; accepting a new
compiler/runtime/manager requires matching evidence, not a broad inferred range.

Primary contracts reviewed on 2026-11-16:

- [Node archive and bundled npm](https://nodejs.org/en/download/archive/v26.13.1)
- [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)
- [Node module semantics](https://www.typescriptlang.org/docs/handbook/modules/reference.html)
- [Type-aware lint compatibility](https://typescript-eslint.io/users/dependency-versions/)
- [ESLint 10](https://eslint.org/blog/2026/02/eslint-v10.0.0-released/)
- [Prettier 3.10](https://prettier.io/blog/2026/11/11/3.10.0)

## Metadata and command adapter

Each selected component owns package.json, package-lock.json v3 and tsconfig.json.
The package explicitly declares type module or commonjs, packageManager
`npm@11.20.0` (an integrity suffix is permitted), and engines.node
`>=26.13.1 <27`. These are declarations: doctor never launches Node/npm to verify
versions, evaluates configuration modules or loads .env. Real acceptance observes
the actual runtime versions separately. Dependency installation is a separate,
reviewed `npm ci` operation, never an init/doctor/validation side effect supplied
by Lean-SDD. Project scripts themselves may have effects and must be reviewed.

Each of types, lint, format, tests and build must have exactly one required check
at the component root. Its argv is exactly `["npm", "run", "<script>"]`; flags such
as --if-present are rejected. Default script names are typecheck, lint,
format:check, test and build. Explicit mappings may name existing reviewed scripts
and retain their tools. A nonempty script is not proof that it checks its claimed
category; human review and real executable acceptance remain necessary.

The metadata checker accepts a self-contained tsconfig with JSON comments and
trailing commas. Require strict, noEmitOnError and declaration true, no individually
disabled strict checks, module/moduleResolution NodeNext and explicit target
ES2023. Require explicit normalized rootDir/outDir inside the component and root
src. Emitted application/declaration output remains under src (for example
src/.build in a root project). Inheritance, project references and alternative
output overrides require separate support; no metadata is rewritten to conform.

Missing application metadata is a doctor warning but blocks validation. Malformed,
unsafe, oversized, inaccessible or incompatible metadata fails. Reads are bounded
to 1 MiB for package/tsconfig and 8 MiB for package-lock. JSON duplicate fields and
non-finite constants are rejected. Other package-manager lockfiles are conflicts.
Root lock metadata is compared with the manifest; this is not dependency-graph,
lock freshness, compiler configuration equivalence or installed-module verification.
Review npm ci and the actual commands for that evidence. Symlink/path checks are
not a sandbox against concurrent hostile filesystem changes.

## Initialization and ownership

For an existing conforming TypeScript project:

```console
lean-sdd init /path/to/project --language typescript --dry-run
lean-sdd init /path/to/project --language typescript
lean-sdd doctor /path/to/project
# After reviewing the installed rules and project commands:
lean-sdd validate /path/to/project
```

The generated root plan contains five required 300-second checks, all with cwd
`.`. Their names sort as typescript-build, typescript-format, typescript-lint,
typescript-tests and typescript-types. Defaults map to npm scripts as follows:

| Category | Exact default argv |
| --- | --- |
| types | `["npm", "run", "typecheck"]` |
| lint | `["npm", "run", "lint"]` |
| format | `["npm", "run", "format:check"]` |
| tests | `["npm", "run", "test"]` |
| build | `["npm", "run", "build"]` |

Choose reviewed scripts that perform the named checks, for example `tsc --noEmit`,
type-aware ESLint, `prettier --check`, behavioral tests and `tsc`. Validation does
not interpret scripts: npm also executes any configured lifecycle hooks. Review
those hooks and their effects. Prepare dependencies separately with the pinned npm
and `npm ci`; initialization and doctor never do that for you.

Init composes common plus selected profile resources and may generate only
lean-sdd.toml. It preserves package.json, tsconfig, lockfiles, source, tests and
existing TOML bytes. Original installation hashes remain immutable. Adding the
profile to an existing Python installation needs separately reviewed migration;
changing --language or editing TOML does not install additional profile assets.

Multiple TypeScript components, Python/TypeScript components and one component
with both profiles use the same mapping model. Every selected profile's required
checks remain mandatory. No root Python fallback applies to TypeScript metadata.
An interaction test must exchange and validate a real message between languages.
For example, a Python API at `src/api` and a TypeScript worker at `src/worker`
each keep their manifests at the component root and source in the component's
`src/`. Map the API's four Python checks and the worker's five npm checks with
their respective cwd values. Put a required interaction test after the worker's
build in check-name order. Two TypeScript components use the same structure,
each with five checks. A single component with `profiles = ["python", "typescript"]`
retains all nine checks and both sets of metadata; it cannot waive either profile.

## Reproducing acceptance

The real suite covers root ESM and CommonJS, two TypeScript components, separate
Python/TypeScript components, and both profiles on one component. Python sends a
versioned JSON request to a real Node process; both sides validate runtime data.
The suite verifies emitted JavaScript/declarations and deliberately fails each
mandatory category to prove failure propagation. Normal unit tests separately
cover metadata errors, preserved ownership, mandatory checks and non-execution.
Wheel and sdist tests verify installed resources and CLI selection without a
checkout. No live GitHub operations are part of this acceptance.

The repository's opt-in command is `uv run pytest --run-typescript
tests/test_typescript_toolchain.py -v`. It requires the exact installed tools and
the committed npm-generated fixture lock. Ordinary pytest runs skip this external
suite explicitly; skipped cases are not new acceptance evidence. Fixture setup
instructions are in tests/fixtures/typescript/README.md. The tested platform is
Linux x86_64; no separate native Windows/macOS run is claimed.
