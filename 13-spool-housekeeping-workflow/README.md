# Artifact 13 — z/OSMF Spool Housekeeping Monitor Workflow

A z/OSMF **Workflow** for lightweight JES spool housekeeping: one step
submits an SDSF-driven JCL probe that surfaces current spool utilization
and the largest spool consumers, a review step has the operator inspect
which owners or jobs dominate spool usage, and a final shell-JCL step
prints a standard housekeeping recommendation sheet.

## What it demonstrates

- **Operational housekeeping workflow** — not just a technical demo, but
  a repeatable runbook for spool pressure triage.
- **SDSF from workflow JCL** — the first step submits `IKJEFT01` and runs
  `SDSF` commands so the spool summary and largest jobs land directly in
  the step's JES output.
- **Sorted spool review** — the SDSF commands sort by spool percent and
  limit the display to the top `TOP_N` consumers so the operator can see
  likely cleanup candidates quickly.
- **Human-in-the-loop decisioning** — the workflow keeps the actual purge
  or escalation choice with operations, where site policy normally
  belongs.
- **Actionable recommendation output** — the last step produces a compact
  checklist covering purge, offload, workload correction, and escalation.

## Layout

```
13-spool-housekeeping-workflow/
  workflow/
    spool_housekeeping.xml  <- workflow definition (1 JCL + 1 review + 1 shell-JCL step)
```

## Running it (Zowe CLI)

```bash
# 1. Upload the workflow XML in binary mode under /z/andre.
zowe zos-files upload file-to-uss workflow/spool_housekeeping.xml \
  /z/andre/spool_housekeeping.xml --binary

# 2. Register and optionally override the defaults.
zowe zos-workflows create workflow-from-uss-file "Spool Housekeeping Monitor" \
  --uss-file /z/andre/spool_housekeeping.xml --system-name ZOS31 \
  --owner andre --assign-to-owner \
  --variables "SPOOL_HIGH_WATER=80,TOP_N=10"

# 3. Validate the workflow renders correctly.
zowe zos-workflows list active-workflow-details --workflow-key <key> --steps-summary-only

# 4. Run the steps in order.
zowe zos-workflows start workflow-step captureSpoolSummary       --workflow-key <key>
zowe zos-workflows start workflow-step reviewFindings           --workflow-key <key>
zowe zos-workflows start workflow-step housekeepingRecommendation --workflow-key <key>
```

## Intended outcome

After `captureSpoolSummary`, the operator should have enough evidence in
spool to answer three questions:

1. What percent of spool is currently in use?
2. Which owners or jobs are the largest contributors?
3. Is immediate housekeeping needed, or is this normal workload shape?

The last step then prints the standard recommendation so the workflow
itself doubles as the operational checklist.
