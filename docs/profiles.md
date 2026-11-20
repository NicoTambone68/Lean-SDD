# Bundled profile resources

The resource API composes shared governance and explicitly selected language
profiles into a deterministic mapping of destination paths to bytes. Python and
TypeScript are production profiles. Extra profiles used by tests are inert fixtures,
not advertised language support. There is no dynamic plugin system, downloaded
metadata, arbitrary import, or command execution during composition.

Fresh initialization uses `resolve_bundle()` for the composed payload and writes
schema-2 installation records. `template_files()` remains the legacy Python
adapter for schema-1 reinitialization and diagnostics; its layout remains readable and historical
records are unchanged. Current reference bytes follow the CLI release; they are
never written over historical installations. Resource resolution itself does not install files or
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
  typescript/
    standards.md
    guide.md
```

`pyproject.toml` maps each source explicitly to one packaged location. Runtime
loading uses `importlib.resources`; it does not search for a checkout. Wheel
tests check the exact resource set and source bytes, compose from ZIP resources,
rebuild a wheel from the sdist, and resolve profiles in an isolated installation.
Only the explicitly included documentation, configuration, and runtime source
enter the distributions; credentials and live acceptance evidence stay excluded.

| Asset | Authoritative source | Installed destination |
| --- | --- | --- |
| Constitution | root `CONSTITUTION.md`, including explicitly approved amendments | `CONSTITUTION.md` |
| Workflow and six core skills | root `AGENTS.md` and explicitly listed `.agents/` assets | original paths |
| Shared standards | `src/lean_sdd/template_overrides/common-standards.md` | `CODING_STANDARDS.md` in composed bundles |
| Python rules | root `CODING_STANDARDS.md`, unchanged | `.agents/standards/python.md` in composed bundles; `CODING_STANDARDS.md` in legacy output |
| TypeScript rules and toolchain guide | explicit `src/lean_sdd/template_overrides/` and `docs/typescript.md` sources | `.agents/standards/typescript.md` and `.agents/docs/typescript.md` |
| Configuration/profile/diagnostic/execution references | `docs/` sources, explicitly mapped | `.agents/docs/` |
| Local ignore rules | `src/lean_sdd/template_overrides/gitignore` | `.agents/.gitignore` |

Reusing root Python standards prevents a second normative copy from drifting.
The setup document also relocates exactly four `../docs/` reference links to
installed `.agents/docs/` links, rejecting unexpected source markup. No normative
text changes during that relocation.

When installing the Python standards at `.agents/standards/python.md`, the resolver changes
only the two Markdown links targeting `CONSTITUTION.md` and `AGENTS.md` to reach
the same root documents through `../../`. It requires exactly one occurrence of
each original link; unexpected source changes fail for review. The text of every
Python requirement remains identical, as verified by a full-document comparison.

The common standards contain exactly one literal `{{profile_standards}}` marker.
Composition replaces it with links to the selected profiles' canonical standards
paths, sorted by profile ID. This is a fixed text substitution, not an executable
template language. Shared standards explicitly require reading every applicable
profile and reporting contradictions before implementation.

The root workflow explicitly loads shared and applicable profile standards and
uses reviewed `lean-sdd validate .` for composed installations. This source
repository and legacy Python installs retain the four maintenance commands.
All approval/failure gates are shared. Inert fixture bundles demonstrate contracts;
they are not supported non-Python installations.

## Typed metadata

`Profile` keeps its identity, display name, and mandatory checks from the
configuration contract, and additionally declares:

- `tools`: a tuple of unique tool identifiers, describing requirements without
  checking for or launching those tools. Python declares `python`, `uv`, `pytest`,
  `ruff`, and `mypy`; TypeScript declares `node` and `npm`. uv remains a shared
  workflow requirement too.
- `diagnostic`: the built-in `python` or `typescript` dispatch key, or `None`
  for inert fixtures. It is never a module name or callable. Doctor dispatches
  the selected profile's checks at each component root and reports unavailable
  application diagnostics for `None`. A new production diagnostic requires an
  explicit code change and acceptance; a different profile cannot borrow either built-in
  diagnostic. See the [diagnostic reference](diagnostics.md).
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
new common standards template. This preserves the legacy layout and does not update an existing installation.
It is not an override permission for profiles. The pinned historical manifest
protects unchanged rules/scripts; separately reviewed documentation changes and
new reference documents belong to the new release. Doctor compares historical
hashes to original files separately from the current release reference.

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

Tests compare the complete relocated Python document to the canonical source
and common assets across legacy/composed reference bundles. Configuration-aware
init/doctor/validate and schema-2 writing are implemented. Automatic migration,
new languages and constitutional amendments remain separately scoped work.

## Adding a future bundled profile

Define its typed requirements, approved standards, tools, diagnostic contract,
explicit resource mappings, and additional skill declarations. Store new template
sources under `src/`, add each asset to the wheel mappings and sdist allowlist,
and provide composition/failure tests. Verify links, Bash syntax when applicable,
the core skill set plus declared additions, and isolated distribution loading.
Provide actual language-toolchain acceptance before adding a production registry
entry. Test fixtures alone never establish supported-language status.

A profile-authoring issue must name its supported platforms/runtime/toolchain,
mandatory categories, exact commands and dependency reproducibility contract.
Extend the static registry, strict configuration requirements and built-in
diagnostic dispatch in `src/lean_sdd/`; metadata cannot import a plugin or execute
a callback. Keep existing Python normative text and all common governance intact.
Review semantic conflicts across every supported combination; structural collision
checks cannot verify prose. Test multiple profiles per component, cross-component
required failures, package imports, artifact composition and actual toolchain
execution before advertising support through `languages`.

[Constitutional clarification #10](https://github.com/NicoTambone68/Lean-SDD/issues/10)
was separately approved and incorporated in Constitution 2.0.1, preserving root
`src/` containment. Template release 0.2.1 includes that authoritative amendment;
existing project constitutions and installation records are not migrated.
[TypeScript support #11](https://github.com/NicoTambone68/Lean-SDD/issues/11)
is included in release 0.3.0 after real Node/npm acceptance. A Python component
at `src/api/` and a TypeScript component at `src/worker/` keep sources inside
their component-local `src/`. Each owns its manifests/lockfile; required interface
tests cover their shared contracts. Two TypeScript components use the same model.
Both profiles on one component keep all nine required checks. The installed
TypeScript profile includes `.agents/docs/typescript.md` with the supported
runtime, package-manager and module contract. See also the
[configuration examples](configuration.md).
