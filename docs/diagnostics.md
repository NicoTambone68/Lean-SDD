# Local diagnostic reference

`lean-sdd doctor [directory]` inspects an initialized project without running its
validation commands. The directory defaults to the current working directory.
Exit status is 0 when no observation fails (warnings are permitted), 1 on a
failure, and 2 for invalid CLI syntax. A successful local diagnostic establishes
neither successful application validation nor live GitHub readiness.

## Independent observations

Doctor reports these concerns separately:

1. **Record validity.** Read at most 1,000,000 bytes of regular UTF-8 JSON from
   `.agents/lean-sdd-install.json`, rejecting unsafe paths and invalid schemas.
   Versions 1 and 2 are supported independently of the current profile catalog.
   The report identifies schema and installed profiles. Without a valid record,
   doctor cannot select an installed profile or perform component diagnostics;
   it still reports shared workflow prerequisites.
2. **Original-file integrity.** Inspect every recorded path against its original
   SHA-256 hash. Missing, inaccessible, or unsafe paths fail; differing content
   warns about local modification. Historical files remain inspectable even if
   today's bundle no longer includes them or their profile is unavailable.
3. **Release compatibility.** Compare with the current bundle for the entire
   recorded profile combination, using legacy assets for schema 1. Same-release
   template-manifest contradictions fail. Another release with changed assets
   receives an upgrade advisory describing added, removed, and changed assets;
   identical assets across releases receive a compatibility warning. Unknown
   profiles make compatibility unavailable and fail without invalidating the
   record itself. No available profile is substituted.
4. **Mapping validity.** Resolve current TOML against installed identity through
   the shared configuration contract. Schema-1 and legacy-python records without
   TOML select the implicit root Python component. Configured installations
   require TOML. Invalid TOML, unknown or uninstalled profiles, unsafe paths,
   missing component/check directories, and non-directory roots fail. Profile
   diagnostics are explicitly unavailable until the mapping is valid; the
   record, integrity, compatibility and shared checks remain useful.
5. **Component setup.** Dispatch only built-in diagnostics selected by the static
   profile registry. Each application message identifies its component ID, root,
   and profile, for example `Component api (src/api), profile python: ...`.
   Two Python components are inspected independently. An unrelated root manifest
   cannot satisfy or invalidate a component's metadata. Inert fixture profiles
   with no diagnostic report that application diagnostics are unavailable;
   they never receive Python checks by default.
6. **Shared workflow prerequisites.** Observe Bash, Git, curl, jq, awk, grep,
   mktemp, and uv availability regardless of application profiles. Missing tools
   fail; uv remains required as the workflow's environment-file loader. Check
   Bash's major version, whether the target is a Git worktree root, and the
   inherited exported MCP endpoint/token settings. An absent endpoint or token
   warns; an unsupported endpoint fails. No credential value is printed and
   validity, permissions, push access, and remote policies are not checked.

Profile availability and application setup are not inferred from filenames.
With a valid historical record whose profiles are unavailable, doctor still
reports original-file integrity, explicitly fails compatibility/selection, and
does not claim complete readiness. It does not run Python diagnostics as a fallback.

## Python component observations

For each selected Python component, doctor reads only that component's
`pyproject.toml`, up to 1 MiB plus one byte to detect oversize. Unsafe or special
files, read errors, invalid UTF-8, invalid TOML (including excessive parser
nesting), oversized input, or a non-table `project` entry fail. Missing
`pyproject.toml` or missing `[project]` metadata warns. A `[project]` table is a
presence check, not full package-metadata, dependency, or build-system validation.
No build backend is imported.

Doctor checks for a regular `uv.lock` at each Python component root and reads
one byte. A successful read confirms the file is readable and nonempty,
regardless of its size. A missing lockfile warns. An empty file, unsafe path,
or read error fails. Dependency resolution and lock freshness are uv's responsibility.
A metadata failure in one component does not suppress another component's
observations or that component's independent lockfile observation.

Application scaffolding remains optional during workflow adoption, so absent
manifests/lockfiles are advisory here. Later validation can require working
project metadata, dependencies, tools, and existing command directories before
it can execute a required check. See the [execution contract](validation.md). A doctor warning is not an exemption from that
validation contract and must never be presented as a passed application check.
Invalid mappings and missing declared component/check directories are already
failures in doctor: the selected location must exist to inspect its setup.

## TypeScript component observations

For each TypeScript component, doctor reads package.json and tsconfig.json (at
most 1 MiB each), plus package-lock.json (at most 8 MiB). Missing files warn;
malformed, oversized, linked, inaccessible or incompatible files fail. tsconfig
may contain comments and trailing commas, but inheritance/references need separate
support. Node/npm declarations, required scripts, strict NodeNext compilation and
source/output containment must match the supported contract. Conflicting manager
locks fail without replacement. Manifest/root-lock metadata must agree.

These are bounded declaration checks, not proof of installed tool versions,
lock freshness, dependency-graph correctness or script behavior. Doctor never
runs Node, npm or configuration modules. A component selecting both profiles gets
both independent sets of diagnostics. The complete profile contract is installed
at `.agents/docs/typescript.md` when TypeScript is selected.

## Configuration edits and historical hashes

A deliberate mapping edit can move or add components within the installed
profile set. It does not upgrade assets or change the release-comparison profile
combination. Doctor reads the current mapping and checks its current directories;
it never copies it into the record or updates original hashes.

Generated `lean-sdd.toml` has an original managed-file hash: editing it can produce
a local-modification warning alongside valid mapping and component results.
Pre-existing user-owned TOML has no installed-file hash, but its mapping remains
required and validated. Doctor compares generated configuration against the
recorded original hash, not today's default configuration, and cannot reconstruct
or certify historical command/mapping contents from that digest.

No diagnostics repair, migrate, upgrade, or rewrite records, configuration,
templates, manifests, lockfiles, or application source. Installing a newer CLI
does not update project templates. Keep the historical record and compare a
fresh installation in a separate directory when reviewing release differences.

## Non-execution boundary

The only child processes are fixed local observations:

- System Bash with `--noprofile --norc -p -c` to print `BASH_VERSION`.
- System Git with `rev-parse --show-toplevel` to observe the local worktree root.

Both have a 10-second timeout and structured arguments. Their executables are
resolved to absolute paths; an executable resolving inside the project is
rejected. Bash startup-file variables and exported functions are excluded.
Git-specific environment overrides, including trace destinations, are removed
so these observations do not redirect the inspected root or create trace files.
Timeouts, inaccessible tools, and invalid tool output encodings produce contextual
failures without losing independent diagnostic results or printing raw output.

Other shared tool checks only inspect PATH availability. No project scripts,
configured argv, build hooks, dependency installation, `.env` loading, or network
requests occur. Credential presence is observed only in the inherited environment.
PATH must name trusted system tools; doctor is not an OS sandbox for malicious
executables or a defense against concurrent hostile filesystem changes. Do not
modify the project or PATH during inspection. File-integrity hashing streams
recorded content without loading whole files into memory.

The Python API is `diagnose(target, registry=BUILTIN_PROFILES) -> list[Check]`.
The explicit in-process registry is for controlled integration and inert tests;
project TOML cannot register executable callbacks, imports, or plugins. Python
and TypeScript are the supported production profiles.
