# Bundled profile resources

The resource API composes shared governance and explicitly selected language
profiles into a deterministic mapping of destination paths to bytes. Python is
the only production profile. Extra profiles used by tests are inert fixtures,
not advertised language support. There is no dynamic plugin system, downloaded
metadata, arbitrary import, or command execution during composition.

Fresh initialization uses `resolve_bundle()` for the composed payload and writes
schema-2 installation records. `template_files()` remains the legacy Python
adapter for schema-1 reinitialization and diagnostics; its bytes and historical
records are unchanged. Resource resolution itself does not install files or
rewrite records. See the [configuration contract](configuration.md) for selection,
configuration ownership, and repeat-initialization behavior.

## Resource layout and authority

The wheel resource namespace is `lean_sdd_templates`:

```text
common/
  AGENTS.md
  CONSTITUTION.md
  CODING_STANDARDS.md
  .agents/                    # existing core skills, helpers and setup documents
profiles/
  python/
    standards.md
```

`pyproject.toml` maps each source explicitly to one packaged location. Runtime
loading uses `importlib.resources`; it does not search for a checkout. Wheel
tests check the exact resource set and source bytes, compose from ZIP resources,
rebuild a wheel from the sdist, and resolve profiles in an isolated installation.
Only the explicitly included documentation, configuration, and runtime source
enter the distributions; credentials and live acceptance evidence stay excluded.

| Asset | Authoritative source | Installed destination |
| --- | --- | --- |
| Constitution | root `CONSTITUTION.md`, unchanged | `CONSTITUTION.md` |
| Workflow and six core skills | root `AGENTS.md` and explicitly listed `.agents/` assets, unchanged | original paths |
| Shared standards | `src/lean_sdd/template_overrides/common-standards.md` | `CODING_STANDARDS.md` in composed bundles |
| Python rules | root `CODING_STANDARDS.md`, unchanged | `.agents/standards/python.md` in composed bundles; `CODING_STANDARDS.md` in legacy output |
| Generic readiness and ignore rules | existing files under `src/lean_sdd/template_overrides/` | original `.agents/` destinations |

Reusing root Python standards prevents a second normative copy from drifting.
When installing their bytes at `.agents/standards/python.md`, the resolver changes
only the two Markdown links targeting `CONSTITUTION.md` and `AGENTS.md` to reach
the same root documents through `../../`. It requires exactly one occurrence of
each original link; unexpected source changes fail for review. The text of every
Python requirement remains identical, as verified by a full-document comparison.

The common standards contain exactly one literal `{{profile_standards}}` marker.
Composition replaces it with links to the selected profiles' canonical standards
paths, sorted by profile ID. This is a fixed text substitution, not an executable
template language. Shared standards explicitly require reading every applicable
profile and reporting contradictions before implementation.

The bundled root workflow retains its existing Python validation commands and
all approval/failure gates during this foundation increment. No nonexistent
validation command is referenced. General application-validation integration
belongs to the later workflow task; fixture-only bundles are not a supported
non-Python installation.

## Typed metadata

`Profile` keeps its identity, display name, and mandatory checks from the
configuration contract, and additionally declares:

- `tools`: a tuple of unique tool identifiers, describing requirements without
  checking for or launching those tools. Python declares `python`, `uv`, `pytest`,
  `ruff`, and `mypy`; uv remains a shared workflow requirement too.
- `diagnostic`: a built-in dispatch key, currently `python` for the Python profile
  or `None` for inert fixtures. It is never a module name or callable. The doctor
  integration is separate work. A new production diagnostic requires an explicit
  code change and acceptance; a different profile cannot borrow Python diagnostics.
- `resources`: explicit `Resource(source, destination)` values. Source paths are
  relative to packaged `profiles/<id>/`; destinations are repository-relative.
  A composable profile must include `.agents/standards/<id>.md` with nonempty UTF-8
  text. A contract-only fixture may omit resources but cannot then be composed.
- `skills`: unique additional skill IDs. Each must contribute its
  `.agents/skills/<id>/SKILL.md` and declare any supporting files in `resources`.
  All six core skill IDs remain mandatory and cannot be shadowed. Only scripts
  actually supplied by the release can be included; metadata executes nothing.

Profile versions follow `package_version()` (the CLI release) for this increment.
Each `ResolvedBundle` contains `template_version`, the sorted unique selected
`profiles`, and a read-only `payload`. `dict(bundle.payload)` makes an owned copy
for an installer. Profile selection is never inferred from application filenames.
Repeated selections resolve to a union; unsupported or empty selections fail.

## Composition and failure contracts

`resolve_bundle(selected_profiles=("python",), registry=..., resource_root=None)`
reads packaged common resources and selected profile trees, checking that each
profile tree exactly matches its declared source paths. The optional explicit
`resource_root` adapter supports local fixtures and archive tests; it is not
supplied by project configuration and does not import code.

`compose_bundle(common, contributions, template_version=..., registry=...)` is the
pure layer. Contributions are mappings from profile ID to destination bytes.
Every contributed destination must be declared in that profile's metadata.
All required common files must already be present; profiles cannot supply missing
governance or core scripts. Both APIs validate:

- Portable, normalized relative paths, without traversal or unsafe names.
- No credentials, installation-record output, Git metadata, environment folders,
  Python caches, or bytecode in resource paths. `.env.example` remains permitted.
- No destination duplicates, case-folded aliases, or file/directory conflicts.
  Even identical content at a colliding destination is rejected.
- Nonempty required root documents and core workflow files; present, nonempty
  profile standards; core skills plus exactly the declared additions.
- No profile additions to shared `.agents/lib/` helpers or undeclared skill trees.
- UTF-8 Markdown and resolvable inline relative file links in every document.
  Anchor targets are not checked; external links are not fetched. Authors should
  use the repository's simple inline-link style, not Markdown reference links
  or links requiring a full Markdown renderer.

Resource trees reject symlinks and special files. Loading is bounded to 1 MiB per
file, 8 MiB per tree/final bundle, 512 entries per tree and 512 final files, with
directory depth limited to 32. Bytes and final destinations are sorted before
being returned. Importing modules performs no application I/O, and resolving
resources does not mutate inputs, write files, run tools, or contact services.

The loader and lexical path validator do not provide an operating-system sandbox
against concurrent malicious filesystem mutation. Bundled assets and in-process
metadata are release-owned inputs; do not mutate them concurrently with reads.
Semantic conflicts in natural-language standards require author review. Structural
collision checks do not prove that arbitrary prose preserves every policy.

### Deliberate replacement boundary

Profiles have no override flag: all profile replacements are rejected. The only
compatibility adapter is `template_files()`, which deliberately chooses the
canonical original Python standards as root `CODING_STANDARDS.md` instead of the
new common standards template. This reproduces the original legacy payload and
does not update an existing installation. It is not an override permission for
profiles. A pinned manifest fixture verifies every legacy destination and hash.

Any future deliberate replacement needs its own reviewed contract and may not
weaken shared governance. New executable template sources belong under `src/`;
the established Bash workflow assets are reused, not copied per language.

## Python rule traceability

Every section and bullet of the authoritative Python coding standards remains
in the Python profile, with the same wording and strength. General requirements
also appear in the shared standards as cumulative rules; the Python text is not
shortened to remove apparent duplication.

| Existing section | Preserved location |
| --- | --- |
| 1. Readability and Design | `.agents/standards/python.md`, section 1 |
| 2. Types and Interfaces | `.agents/standards/python.md`, section 2 |
| 3. Documentation | `.agents/standards/python.md`, section 3 |
| 4. Data and Numerical Semantics | `.agents/standards/python.md`, section 4 |
| 5. Errors and Resource Management | `.agents/standards/python.md`, section 5 |
| 6. Python Runtime Practices | `.agents/standards/python.md`, section 6 |
| 7. Security and Diagnostics | `.agents/standards/python.md`, section 7 |
| 8. Testing | `.agents/standards/python.md`, section 8 |
| 9. Packaging, Dependencies, and Compatibility | `.agents/standards/python.md`, section 9 |
| 10. Static Quality and Performance | `.agents/standards/python.md`, section 10 |

Tests compare the complete relocated Python document to the canonical source,
and every common workflow file to its legacy bytes. Governance amendments,
language activation in init/doctor, version-2 record writing, and migration remain
separately scoped tasks.

## Adding a future bundled profile

Define its typed requirements, approved standards, tools, diagnostic contract,
explicit resource mappings, and additional skill declarations. Store new template
sources under `src/`, add each asset to the wheel mappings and sdist allowlist,
and provide composition/failure tests. Verify links, Bash syntax when applicable,
the core skill set plus declared additions, and isolated distribution loading.
Provide actual language-toolchain acceptance before adding a production registry
entry. Test fixtures alone never establish supported-language status.
