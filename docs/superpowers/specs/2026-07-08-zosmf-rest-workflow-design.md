# Design — Artifact 11: z/OSMF Self-Inventory Workflow (`rest` + `setVariable`)

Date: 2026-07-08
Status: awaiting user approval
Target repo folder: `11-rest-workflow/`
Host location for workflow files: `/z/andre` (per user instruction)

## Purpose

A z/OSMF workflow that interrogates the z/OSMF instance it runs on
through REST steps, captures pieces of the responses into workflow
variables, and ends with a report step built entirely from captured
values. It completes the action-type trilogy: artifacts 9/10 used
`template` in all three flavors (JCL, TSO-REXX, shell-JCL); this one
exercises `rest` and `setVariable`, the two remaining step action
types in the workflow schema.

## Workflow shape (4 steps)

| # | Step | Action type | What it does |
|---|------|-------------|--------------|
| 1 | `getInfo` | rest | `GET /zosmf/info`; capture z/OSMF version (and plugin count if capturable) into output variables |
| 2 | `deriveNames` | setVariable | Build a timestamped report name from captured values |
| 3 | `submitProbe` | rest | `POST /zosmf/restjobs/jobs` submitting a trivial job; capture returned `jobid` |
| 4 | `writeReport` | template (shell-JCL) | Echo the inventory (version, plugin count, JOBID, report name) — proves captured variables flow across action types |

Steps chained with `prereqStep`, `autoEnable` on, flat leaf steps
(the structure that validates most reliably).

## Discovery-first approach

The `rest` element's exact children (HTTP method, URI, request body,
response-capture / output-processing syntax) are the least-documented
part of the schema, and past artifacts showed that guessing gets
punished by the validator. Step zero, before writing any XML:

1. Download `workflow_v1.xsd` from the host (the schema referenced by
   every workflow) and read the `rest` and `setVariable` type
   definitions.
2. Pull IBM sample workflows from `/Z31RS1/usr/lpp/zosmf/samples`
   (the product filesystem's mount point on ZOS31) and grep
   for real `rest` / `setVariable` usage (note: XMLs there are tagged
   ISO8859-1 — pipe through `iconv -f ISO8859-1 -t IBM-1047` before
   grepping).
3. Only then author the workflow XML against observed syntax.

**Graceful degradation:** if response capture turns out to be more
limited than hoped (e.g. "advanced output processing" is awkward or
absent on z/OS 3.1), reduce scope rather than fake it — e.g. step 1
becomes a rest call judged by status code only, and `deriveNames`
demonstrates `setVariable` from literals/other variables. The
DESIGN.md then documents what the schema actually allows; a negative
finding is still portfolio material.

## Host layout

- Workflow XML uploaded to `/z/andre/rest-inventory.xml` (uploaded
  `--binary`, like all workflow XML).
- No fileTemplate/side files expected; if one becomes necessary it
  also goes directly in `/z/andre` (normal text upload, EBCDIC).

## Repo artifact layout

```
11-rest-workflow/
  workflow/
    rest-inventory.xml   <- workflow definition
  docs/
    DESIGN.md            <- schema findings, error-code archaeology
  README.md              <- what it demonstrates, run instructions, verified-run evidence
```

Top-level `README.md` (table + layout) and `CLAUDE.md` (scope +
status) updated to 11 artifacts, matching the pattern used for
artifact 10.

## Verification

Same loop as artifacts 9/10, run from this Windows workspace via
Zowe CLI (PowerShell, not Git Bash, for USS paths):

1. `zowe zos-files upload file-to-uss ... --binary`
2. `zowe zos-workflows create workflow-from-uss-file "REST Inventory"
   --system-name ZOS31 --owner andre --assign-to-owner --variables ...`
   (defaults do not resolve headless substitution)
3. `--steps-summary-only` as the fast full-template-evaluation gate
4. Run steps in order; record step states and any JOBIDs
5. Quote step/spool output as evidence in the README

Open question to answer empirically (and document): whether rest
steps run under the registering user's credentials or need explicit
auth configuration.

## Risks

- **Response capture may not exist as hoped** — mitigated by the
  graceful-degradation plan above.
- **Shared LPAR instance reaping** — re-create instances (new key)
  rather than fight `--overwrite` on in-progress instances.
- **rest step auth** — unknown; treated as a finding either way.

## Success criteria

- Workflow registers cleanly (create succeeds = definition valid).
- All steps reach Complete on ZOS31, with at least one `rest` step
  and one `setVariable` step actually executed.
- At least one value demonstrably flows: captured or set in an early
  step, visibly consumed in the final report step's output.
- Artifact 11 committed and pushed to Mainframe_Shop following repo
  conventions.

## Out of scope

- Anything requiring z/OSMF admin authority (plugin enablement,
  Liberty tuning).
- Off-platform CI (GitHub Actions) — rejected as direction C.
- Console REST API client — rejected as direction B (possible future
  artifact).
