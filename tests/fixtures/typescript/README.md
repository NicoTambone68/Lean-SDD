# Real TypeScript acceptance fixture

This fixture is test data, never an application scaffold installed by Lean-SDD.
Application and executable lint configuration live in its `src/`; emitted code
belongs in `src/.build`. `tests/` contains only test harnesses and assertions.

Use Node 26.13.1 with npm 11.20.0 on Linux. The committed package-lock.json v3 was
generated with that npm and pins the complete dependency graph with registry URLs
and integrity hashes. Direct versions are TypeScript 6.0.3, ESLint 10.14.0,
typescript-eslint 8.72.2 and Prettier 3.10.0. No global compiler/linter is required.

From the repository root, with Node/npm and uv on PATH:

```console
node --version
npm --version
uv run pytest --run-typescript tests/test_typescript_toolchain.py -v
```

This explicit suite performs `npm ci --ignore-scripts --no-audit --no-fund` in
temporary directories, checks actual versions, and executes the five required
categories. It covers ESM, CommonJS, two TypeScript components, mixed Python/TypeScript
components, both profiles on one component, real JSON message exchanges and runtime
rejection, CLI execution, and intentional failures in each required category.
Python checks use the committed frozen uv.lock. Downloads may be needed on a cold
cache; installation belongs only to this explicit acceptance setup and reviewed
Python commands. Neither Lean-SDD init nor doctor installs or runs project tools.

The matrix passed on Linux x86_64 on 2026-11-16. Ordinary `uv run pytest` skips these
external-tool cases. A skipped case is not a new acceptance pass. An explicitly
requested run fails when its tools or lock are missing. The suite uses the actual
built-in registry and default npm adapter.

Regenerate the lock only as part of a separately reviewed dependency change:
from this fixture directory, use the pinned npm with
`npm install --package-lock-only --ignore-scripts --no-audit --no-fund`, review
all changed versions/URLs/integrities, and rerun the full matrix. Do not fabricate
locks or change pins just to bypass a failing check.
