# Component and profile configuration contract

This is the schema-1 foundation for `lean-sdd.toml`. The Python API can parse,
inspect, and resolve it. The current CLI still uses its existing Python-only
initialization and diagnostics: it does not yet consume this configuration,
offer language selection, write version-2 installation records, or execute
configured validation. Those integrations are separate increments. Python is
the only supported bundled profile; selecting TypeScript is an error.

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
No API in this increment runs subprocesses, reads `.env`, installs dependencies,
contacts a service, changes process environment, or writes project files.

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
validation. Version-2 serialization and initializer integration are later work.

### Proposed version-2 installation record contract

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

This is a shape illustration, not a valid installation record or a claim that
version-2 serialization is implemented. `files` records original managed bytes,
not command definitions or current component mappings. If init generates
`lean-sdd.toml`, its original hash belongs in `files`. If it consumes a
pre-existing user-owned TOML, the file is preserved and not added to that
manifest. `configuration_mode` records the requirement to retain configuration
regardless of who created it. Never update historical hashes after customization.

Version-1 records adapt to `InstallationIdentity(("python",), "legacy-python")`
without rewriting their bytes, hashes, or timestamps. Version-2 older-reader
support is not promised. Updating a CLI does not migrate installations or switch
their profile assets. Fresh installs using explicit mappings require configured
mode; no-config compatibility installs can retain legacy-python mode.

## Complete root Python example

The current CLI does not yet consume this file. It is a valid schema-1 input to
the Python API; creating it does not authorize running any command.

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
