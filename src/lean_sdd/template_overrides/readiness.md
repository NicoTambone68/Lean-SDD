# GitHub workflow readiness

**Status: live acceptance has not been established for this project.** Installing
Lean-SDD and passing `lean-sdd doctor` do not verify GitHub write permissions,
server capabilities, Git push access, or a successful end-to-end workflow.

Follow [setup](README.md) using this project's explicitly selected GitHub
repository and working/base branch. Never reuse a repository, issue, branch,
commit, or approval from an example or another project's acceptance record.

Before claiming readiness, complete an explicitly authorized run in a disposable
project with the actual installed scripts:

1. Record the installer/template version and verify current MCP capabilities
   and identity, independently of Git authentication.
2. Create and read back a real issue with a complete plan. Stop for implementation
   approval, then retrieve the issue again as the authoritative specification.
3. Prepare the selected branch, implement, validate, commit, and record the
   implementation checkpoint. Stop for publication approval.
4. Publish and verify the PR, retain its exact source/base identity and JSON
   result, and record its checkpoint. Stop for separate merge approval.
5. Merge the approved source, verify the remote result and local synchronization,
   record finalization, and separately close and read back the issue.
6. Record actual evidence and any failures without credentials or session IDs.

Follow `AGENTS.md` failure handling at every boundary. Installation, local
checks, simulated approvals, and historical evidence from other repositories
cannot substitute for this run. The installer performs none of these live steps.
