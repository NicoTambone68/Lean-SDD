# Component and profile configuration contract

`lean-sdd.toml` uses configuration schema 1. The API and initializer parse and
resolve explicit component mappings; `lean-sdd languages` lists supported
production profiles and `init --language python` provides a single-root
convenience selection. Fresh installations write installation-record schema 2.
Python is the only supported bundled profile; selecting TypeScript is an error.
Initialization and diagnostics never execute configured validation. Doctor
checks each declared Python component locally; the validation runner remains a
later increment. See the [diagnostic reference](diagnostics.md).

## API and trust boundary

`lean_sdd.profiles` supplies immutable `Profile`, `RequiredCheck`, and
`ProfileRegistry` values. The default static registry contains only Python.
Explicit in-process registries can supply inert fixtures or later bundled
profiles. No modules, plugins, commands, or resources are discovered from project
configuration. The Python entry cannot redefine its mandatory checks.

`lean_sdd.configuration` exposes:

- `parse_configuration(content, registry=...)`: pure parsing and semantic
  validation, returning immutable `Configuration`, `Component`, and `Check`
  values. It does not access the filesystem.
- `load_configuration(root, registry=...)`: bounded local reading of exactly
  `root/lean-sdd.toml`, followed by parsing and path inspection. Only an absent
  file returns `None`; malformed, empty, inaccessible, linked, and special files
  fail with `ConfigurationError`.
- `validate_directories(config, root, require_exists=False)`: inspect all
  component and check paths. Missing directories are permitted during planning;
  existing symlinks and non-directory paths are always errors. With
  `require_exists=True`, all directories must exist. It never creates them.
- `resolve_configuration(root, installed=None, language=None, registry=...)`:
  apply the precedence below and return the configuration plus its provenance.

Use parsed/resolved configurations with `validate_directories`; manually
constructed dataclasses are trusted internal values, not a runtime validation
boundary. Revalidate paths immediately before future execution. Directory checks
cover the root and its ancestors as well as configured descendants. Root paths
containing `..` are rejected. The repository must not be concurrently mutated
during inspection: these checks are not an OS sandbox or a defense against a
hostile process racing filesystem changes. Source containment is a configuration
contract, not a scan of every application file.

Parsing argv is **not execution approval**. Project commands are executable code
even when TOML syntax is valid. The authorized workflow must review the issue,
governing standards, selected profiles, and current command configuration before
explicitly invoking the future validation runner. Reading a repository, importing
these modules, initialization, and diagnostics never confer that authority.
The configuration APIs never run subprocesses, read `.env`, install dependencies,
contact a service, change process environment, or write project files. The
initializer alone writes the selected installation payload after preflight.

Errors identify validated component/check IDs and fields, without printing raw
TOML values or command arguments. Applications should present the contextual
`ConfigurationError` message rather than dump underlying parser/I/O tracebacks.
Configuration is not a secret store: keep credentials out of argv and metadata.

## Schema 1

All listed fields are required except the two explicitly forbidden for project
checks. There are no per-field defaults in explicit configuration. Unknown keys,
duplicate TOML declarations, unsupported schema versions, and incorrect types
are errors. A boolean is not an integer or timeout. Fields are case-sensitive.

| Location | Field | Contract |
| --- | --- | --- |
| Root | `schema_version` | Integer `1` |
| Root | `components` | Nonempty table keyed by component ID |
| Root | `checks` | Nonempty array of tables, written as `[[checks]]` |
| Component | `path` | Normalized relative component root |
| Component | `profiles` | Nonempty array of distinct supported profile IDs |
| Check | `name` | Globally unique stable identifier |
| Check | `scope` | `component` or `project` |
| Component check | `component` | Declared component ID; forbidden for project checks |
| Component check | `profile` | Profile selected by that component; forbidden for project checks |
| Check | `category` | Stable validation category identifier |
| Check | `cwd` | Normalized directory path relative to the repository root |
| Check | `argv` | Nonempty array of strings; first element is a nonblank executable |
| Check | `required` | Boolean |
| Check | `timeout_seconds` | Finite positive integer or float, measured in seconds |

Component/profile/category/check identifiers match `[a-z][a-z0-9_-]{0,63}`.
Profile selections and resolved components are sorted by ID; checks are sorted
by their globally unique name. The resulting profile union is sorted and unique.
Explicit order in TOML does not change this order. Future runners should consume
the complete resolved check tuple; no dependency-selective execution is implied.

The configuration is at most 1 MiB of UTF-8, with at most 128 components and
1,024 checks. The loader verifies a regular file before opening and reads at
most the limit plus one byte. The pure parser also enforces the encoded-size
limit. There is no upper timeout policy beyond finite positive seconds here;
process lifetime enforcement belongs to the subsequent runner. Empty arguments
after argv[0] are valid. NUL and invalid Unicode are forbidden in argv. Shell
metacharacters, spaces, and newlines remain literal arguments, not expressions.

### Source roots and directories

Paths use portable `/` separators and must already be normalized: no absolute
paths, `..`, redundant `.`/separators, trailing slash, backslashes, drive prefixes,
control characters, Windows device names, or trailing dot/space segments. `.`
denotes the repository root. Non-root components must be `src` or descendants
of root `src/`. Each component's application source stays within that component
and root `src/`; for a root component, application source is under `src/`.

For example, `src/api` is a component root containing its manifests and tests;
its Python package can be in `src/api/src/api_package`. The two source levels
are intentional and do not require a flat source layout or a constitution change.

Equal and ancestor/descendant component paths are rejected, including case-folded
aliases for portability. Consequently `.` cannot coexist with other components.
Component-scoped check directories must remain inside their component;
project-scoped directories can be anywhere contained in the repository. Existing
symlinks are rejected even if they target another location inside the repository.

### Mandatory checks and optional additions

For each selected profile of each component, each mandatory category must have
exactly one check with `required = true`. A project check or a different profile's
check cannot satisfy the requirement. Additional categories may be required or
optional. A duplicate mandatory category is an error, even if one copy is optional.

Python has these fixed obligations, all from that component's root:

| Category | Exact argv |
| --- | --- |
| `tests` | `["uv", "run", "pytest"]` |
| `lint` | `["uv", "run", "ruff", "check", "."]` |
| `format` | `["uv", "run", "ruff", "format", "--check", "."]` |
| `types` | `["uv", "run", "mypy", "."]` |

Changing the command, adding flags to the mandatory command, changing its cwd,
omitting a category, or marking it optional is rejected. Add a separate category
for extra checks. Profiles with `RequiredCheck.argv = None` require the category
but permit reviewed concrete argv and a cwd within the component. Profiles with
fixed argv require that exact tuple at the component root. Multiple profiles on
one component keep separate obligations via `(component, profile, category)`;
their checks do not silently replace each other.

## Resolution and installation identity

Explicit TOML is parsed first. An invalid file never falls back, even when a
language option or historical installation would otherwise select Python.

1. A valid explicit mapping selects its profile union. Given an installed
   identity, all installed profiles must be available in the supplied registry,
   and the mapping must select only profiles already installed. The mapping may
   use a subset; this does not delete assets or rewrite installed identity.
2. `language` must name a supported profile. With an explicit mapping, it must
   match the sole profile of a sole component at `.`. Given installed identity,
   the recorded profile set must also be exactly that single selection; the
   option never switches installed assets.
3. An installed `configured` identity requires `lean-sdd.toml`. An absent file
   is an error, including when a matching language option is supplied. Unknown
   installed profiles are an error for resolution, never a reason to choose
   Python. Diagnostics may still inspect recorded asset integrity separately.
4. A legacy Python installation without TOML resolves to one implicit component
   named `root` at `.`, with Python's four checks, each required and with a
   300-second timeout. Provenance is `installed-legacy`.
5. A fresh installation without TOML defaults to that same Python plan;
   provenance is `fresh-default`, or `language` with explicit Python selection.
   Additional fixture profiles require explicit configuration; there is no
   automatic Python fallback or generic scaffold for them.

Any explicit mapping has provenance `explicit`. Mapping/check edits within the
installed set are deliberate configuration changes subject to review; they do
not perform an asset upgrade. The resolver does not infer installed identity by
reading an installation record: callers pass it after independent record
validation. The initializer reads and validates that record before resolution.

### Version-2 installation record contract

The existing record's `schema_version`, `template_version`, and `files` retain
their meanings. Version 2 adds `profiles` (nonempty, sorted, unique valid IDs)
and `configuration_mode` (`legacy-python` or `configured`). Identity is validated
independently of the current profile catalog. `legacy-python` permits exactly
`["python"]`; it preserves the no-TOML compatibility contract. `configured`
requires TOML even if all installed profiles happen to be Python.

```json
{
  "schema_version": 2,
  "template_version": "<actual CLI release>",
  "profiles": ["python"],
  "configuration_mode": "configured",
  "files": {"<installed relative path>": "<original SHA-256>"}
}
```

This is a shape illustration; real records contain the actual release and hashes.
`files` records original managed bytes,
not command definitions or current component mappings. If init generates
`lean-sdd.toml`, its original hash belongs in `files`. If it consumes a
pre-existing user-owned TOML, the file is preserved and not added to that
manifest. `configuration_mode` records the requirement to retain configuration
regardless of who created it. Never update historical hashes after customization.

Version-1 records adapt to `InstallationIdentity(("python",), "legacy-python")`
without rewriting their bytes, hashes, or timestamps. Version-2 older-reader
support is not promised. Updating a CLI does not migrate installations or switch
their profile assets. All fresh installs use configured mode, generating a
configuration when absent. Existing legacy-python records retain their no-TOML
compatibility behavior and are never converted by initialization.

## Initialization and record ownership

`initialize(target, dry_run=False, language=None)` returns `InstallResult` with
`created` (planned on dry-run), `unchanged` (identical managed files), `preserved`
(existing configuration), installed `profiles`, and resolved `configuration`.
The CLI reports profiles and each component ID/path/profile selection on both
real and dry runs. User configuration content and command arguments are not
printed. It never creates application component directories, scaffolding,
dependency manifests, or environments, and never executes configured checks.

On a fresh target, common resources plus the selected profile union form the
managed payload. `--language` never overrides an explicit mapping. Without
TOML, the default Python plan is serialized to `lean-sdd.toml`, including the
four mandatory checks at the root. With TOML, all original bytes, comments,
line endings, and timestamps are preserved. The installer does not serialize
user mappings, including mappings for two Python components.

The schema-2 record contains original hashes of the final managed bytes (after
profile composition and link relocation). If configuration was generated, its
original hash is included; if configuration was pre-existing, it is excluded.
The record does not hash itself or copy current commands/mappings. Its profile
list must be a nonempty sorted array of unique valid IDs; mode is mandatory.
Generated configuration requires configured mode. Case-folded and file/directory
path collisions are invalid. Profile availability is separate from parsing:
a historical record with unavailable profiles is valid data, but init fails
instead of replacing its identity with Python.

Repeat initialization is conservative:

- Schema 1 resolves legacy Python and uses the legacy payload. Its record bytes,
  digest spelling, extra historical fields, and timestamps remain untouched.
  It does not add composed profile assets or generate configuration.
- Schema 2 uses the full recorded profile set, even if the current mapping uses
  a subset. Configured mode requires a valid TOML file; neither a default nor a
  matching language option can replace a missing one. Legacy-python mode still
  permits the implicit root mapping without generating a file.
- The current template release and template manifest must agree with the record.
  Any release difference or template conflict stops all writes; initialization
  is not an upgrade mechanism. Identical managed files are untouched, and missing
  assets may be restored only from the matching release and original manifest.
- Valid deliberate configuration edits within the installed set are preserved.
  Generated configuration remains editable: its original hash is never replaced
  with a hash of the edited file. Doctor reports customization against that hash;
  it cannot reconstruct or certify the original generated mapping from a digest.
  User-owned configuration has no managed-file hash, but is still required and
  validated. Init never repairs, rewrites, or switches the current mapping.

Every managed destination, including generated TOML and the record, is checked
before writes. Conflicts, unsafe paths, and links fail even in dry-run mode.
Real installation uses exclusive file creation and writes the record last.
A write failure cleans up only files and empty directories created by that
invocation, including generated configuration. Cleanup failures report leftover
paths for explicit recovery. Dry runs create neither files nor directories.
The filesystem must not be concurrently modified; this is bounded rollback on
reported failures, not a crash-safe transaction or protection against hostile
filesystem races. After an interrupted process, inspect partial output before
retrying; the installer never assumes an uncertain write can be overwritten.

Older CLI releases need not understand schema 2. Installing a newer CLI does
not update project templates, migrate records, or switch installed profiles.
Compare a fresh installation in a separate directory when reviewing an upgrade.

## Complete root Python example

Save this as `lean-sdd.toml` before initialization to select a root component
named `app`. Creating or parsing it does not authorize running any command.

```toml
schema_version = 1

[components.app]
path = "."
profiles = ["python"]

[[checks]]
name = "app-tests"
scope = "component"
component = "app"
profile = "python"
category = "tests"
cwd = "."
argv = ["uv", "run", "pytest"]
required = true
timeout_seconds = 300

[[checks]]
name = "app-lint"
scope = "component"
component = "app"
profile = "python"
category = "lint"
cwd = "."
argv = ["uv", "run", "ruff", "check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "app-format"
scope = "component"
component = "app"
profile = "python"
category = "format"
cwd = "."
argv = ["uv", "run", "ruff", "format", "--check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "app-types"
scope = "component"
component = "app"
profile = "python"
category = "types"
cwd = "."
argv = ["uv", "run", "mypy", "."]
required = true
timeout_seconds = 300
```

## Complete two-component Python example

This uses two independently configured Python projects. The optional final
project-wide category illustrates interface tests; its command and directory
must be supplied by the application, and no integration scaffold is generated.
Here the integration check is required because the example assumes interacting
components. Each component supplies its own `pyproject.toml`, lockfile, tooling,
and source. Parsing does not require these directories to exist; execution will.

```toml
schema_version = 1

[components.api]
path = "src/api"
profiles = ["python"]

[components.worker]
path = "src/worker"
profiles = ["python"]

[[checks]]
name = "api-tests"
scope = "component"
component = "api"
profile = "python"
category = "tests"
cwd = "src/api"
argv = ["uv", "run", "pytest"]
required = true
timeout_seconds = 300

[[checks]]
name = "api-lint"
scope = "component"
component = "api"
profile = "python"
category = "lint"
cwd = "src/api"
argv = ["uv", "run", "ruff", "check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "api-format"
scope = "component"
component = "api"
profile = "python"
category = "format"
cwd = "src/api"
argv = ["uv", "run", "ruff", "format", "--check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "api-types"
scope = "component"
component = "api"
profile = "python"
category = "types"
cwd = "src/api"
argv = ["uv", "run", "mypy", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "worker-tests"
scope = "component"
component = "worker"
profile = "python"
category = "tests"
cwd = "src/worker"
argv = ["uv", "run", "pytest"]
required = true
timeout_seconds = 300

[[checks]]
name = "worker-lint"
scope = "component"
component = "worker"
profile = "python"
category = "lint"
cwd = "src/worker"
argv = ["uv", "run", "ruff", "check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "worker-format"
scope = "component"
component = "worker"
profile = "python"
category = "format"
cwd = "src/worker"
argv = ["uv", "run", "ruff", "format", "--check", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "worker-types"
scope = "component"
component = "worker"
profile = "python"
category = "types"
cwd = "src/worker"
argv = ["uv", "run", "mypy", "."]
required = true
timeout_seconds = 300

[[checks]]
name = "shared-contracts"
scope = "project"
category = "integration"
cwd = "."
argv = ["uv", "run", "pytest", "tests/integration"]
required = true
timeout_seconds = 600
```
