# Python foundation acceptance

Scope: [parent #3](https://github.com/NicoTambone68/Lean-SDD/issues/3), foundation
increments #4–#9. Python is the only production profile. This is an evidence map,
not a claim of live GitHub readiness or support for future languages. Test names
refer to this release's source distribution; execute the four maintenance checks
to establish results for a particular checkout.

## Parent acceptance traceability

| Parent criterion | Automated evidence / review boundary |
| --- | --- |
| 1. One shared governance layer, explicit standards, conflict handling | `test_profiles.py::test_python_rules_and_common_workflow_are_preserved`; `test_workflow_acceptance.py::test_workflow_gates_and_execution_boundary`; author review must still resolve contradictory prose. |
| 2. Legacy Python without forced migration; multiple Python components | `test_profile_installation.py`, `test_distribution.py::test_wheel_and_sdist_install_without_checkout`; historical record bytes/timestamps remain unchanged; both artifacts execute root and multiple-component checks. |
| 3. Strict mappings: roots, profile unions, duplicates, overlaps, paths, symlinks, cwd | `test_configuration.py`, `test_validation.py`; malformed explicit data never defaults to Python. |
| 4. Explicit selection/reporting; TypeScript rejected | `test_profile_installation.py::test_languages_and_cli_selection`, `test_unsupported_languages_do_not_default_or_write`; isolated artifact acceptance checks the same CLI boundary. |
| 5. Dry-run, repeats, conflicts, user config, secrets, links, rollback | `test_installer.py`, `test_profile_installation.py`; distribution dry-run/repeat/ownership tests and seeded package-exclusion sentinels. |
| 6. Schema 1/2 historical hashes and distinct diagnostic observations | `test_templates.py`, `test_doctor.py`, `test_profile_installation.py`; isolated artifact historical/current manifests, modified/missing files, unknown identity and no-migration acceptance. |
| 7. Local, non-executing component diagnostics; no unknown-profile Python fallback | `test_doctor.py`; isolated artifact doctor and validation preflight distinguish advisory application setup from blocking failures. |
| 8. Explicit argv/cwd, full required suite, nonzero/timeout/cancel/missing/not-run | `test_validation.py` exercises real inert process groups and CLI signals; artifact acceptance executes root/multi Python checks and propagates required project-check failure. Configuration tests reject missing/optional mandatory categories. |
| 9. Multiple inert profiles and mixed orchestration | `test_profiles.py`, `test_validation.py`, `test_workflow_acceptance.py::test_inert_profile_bundle_contract`; fixtures establish architecture only, without TypeScript/toolchain or live credentials. |
| 10. Bundle links, Bash syntax, unchanged gates, skills plus declared additions | `test_distribution.py::test_bundled_links_resolve_and_scripts_parse`, `test_workflow_acceptance.py`; original script hashes and Python rules remain pinned. |
| 11. Wheel/sdist completeness, isolated commands, rebuild without checkout | `test_distribution.py::test_wheel_and_sdist_install_without_checkout` runs the command matrix for both the direct wheel and the sdist-rebuilt wheel, with standard imports and explicit resource identities. |
| 12. Root/multiple Python examples, future mixed layout and staged roadmap | [configuration examples](configuration.md), [profile authoring and roadmap](profiles.md); tests parse and run the documented Python check plans against inert tools. |

## Release and manual review

Release 0.2.0 revised workflow/setup documentation and added installed references
under `.agents/docs/`. That foundation increment left the root constitution and
Python standards unchanged. Each package resource has one authoritative source and explicit wheel
mapping; setup links and Python standards' two root links are relocated only for
installation. Runtime code stays under `src/`. The sdist includes tests and these
references so it can rebuild the same runtime/resources independently.

The historical 0.1.0 manifest remains in the tests. Unchanged rules, scripts and
other original assets retain their hashes. A newer CLI reads old records but
never updates files, hashes, mappings or timestamps. Init refuses cross-release
repair/upgrade; compare a fresh installation and plan any manual migration
separately. Old CLIs need not read schema 2. Existing installations retain their
original workflow until explicitly migrated.

Review the installed AGENTS, common/profile standards, setup and skill documents
as a coherent whole. The tests protect key gate clauses and byte-identical core
scripts, but cannot prove that natural-language instructions will be followed.
The complete final required suite includes all components and required integration
checks; optional failures must stay visible. Command review precedes execution,
including when configuration edits are themselves the issue being implemented.

## Separately approved governance clarification

[Issue #10](https://github.com/NicoTambone68/Lean-SDD/issues/10) applies the explicitly
approved Principle III clarification as Constitution 2.0.1, dated 2026-11-16.
It distinguishes repository roots, component roots and component-local source
roots without changing source containment or coupling component count to language
count. Root Python, two Python components and future mixed-language examples all
keep application/runtime/generated code under repository root `src/`.

Template release 0.2.1 distinguishes the amended asset from release 0.2.0. Existing
installations retain their original constitution and hashes; adoption requires a
separately reviewed manual change. Python standards, runtime behavior and workflow
gates are unchanged. The policy test retains the historical manifest and pins the
approved amended constitution; distribution tests verify the same source bytes in
both artifact formats. This follow-up does not change the historical #9 scope.

## Deferred acceptance

- [TypeScript #11](https://github.com/NicoTambone68/Lean-SDD/issues/11): standards, real toolchain, TypeScript-only and Python/TypeScript interface acceptance. No fixture or future layout proves this support.
- Other languages, application scaffolds, dynamic/downloaded profiles, automatic migration/profile switching and dependency-based final-check selection remain out of scope.
- Validation is Linux-only (including Linux under WSL); native Windows/macOS execution acceptance is not supplied. Owned process-group cleanup is not a sandbox; detached descendants/services are unsupported.
- Live GitHub permissions, expected-head policy enforcement and end-to-end issue/PR/merge/closure require a separately authorized run with actual installed scripts, approvals and retained evidence. Inert tests, doctor and this matrix do not establish them. This issue does not close parent #3 automatically.
