# Artifact 11 — z/OSMF Self-Inventory Workflow (rest + setVariable)

A z/OSMF **Workflow** that completes the step action-type trilogy
(`template`, `rest`, `setVariable`): a `rest` step calls z/OSMF's own
info API and captures the version into a variable, a `setVariable` step
derives a report name from it, a second `rest` step submits an IEFBR14
probe job through the jobs REST API and captures the returned JOBID,
and a final shell-JCL step prints an inventory report that proves every
value flowed across step types.

Verified on a real z/OS 3.1 system (z/OSMF workflow engine, ITSCPLEX /
ZOS31, 2026-07-09): all four steps Complete — `getInfo` HTTP 200,
`deriveNames` derived `inventory-1`, `submitProbe` HTTP 201 with probe
job `JOB07083` (CC 0000), and report job `JOB07085` printed
`SUCCESS: variables flowed across step types` on its spool.

## What it demonstrates

- **rest workflow steps** — the workflow engine itself issues HTTP
  calls, judged by `expectedStatusCode`, with response values captured
  into instance variables via `propertyMapping`. The mapping content is
  a bracket-notation JSON path (`["api_version"]`, `["jobid"]`) — a
  bare property name fails registration with `IZUWF8017E`.
- **actualStatusCode capture** — the probe step also stores the real
  HTTP status (`201`) into a variable via
  `<actualStatusCode mapTo="PROBE_STATUS"/>`, a self-documenting
  diagnostic if the call ever drifts from the expected code.
- **setVariable steps** — a step whose only action is
  `<setVariable name="REPORT_NAME" substitution="true">` deriving a new
  value from an earlier rest capture; simpleContent, no `expression`
  child (that syntax is a common hallucination — the XSD is the truth).
- **Cross-step variable flow** — rest capture → setVariable derivation
  → rest job-submit capture → shell-JCL report; four steps, three
  action types, one variable namespace.
- **The self-call TLS trap** — with no `hostname` in the XML, the
  engine calls itself using the host *from the URL the client used to
  start the step*. Connect by IP and the call dies on certificate SAN
  matching; connect by DNS name and it works. Hardcoding
  scheme/hostname in the XML instead forces the credentialed
  remote-z/OSMF path (`IZUWF8053E`), which this system's engine login
  refuses — the full dead-end map is in `docs/DESIGN.md`.

## Layout

```
11-rest-workflow/
  workflow/
    rest-inventory.xml  <- workflow definition (2 rest + 1 setVariable + 1 shell-JCL step)
  docs/
    DESIGN.md           <- XSD findings, error archaeology, verified-run evidence
```

## Running it (Zowe CLI)

```bash
# 0. Connect by DNS hostname, not IP: the engine reuses your host for
#    its self-calls and the server cert has no IP SAN (see DESIGN.md).
HOST=zos31.pok.stglabs.ibm.com

# 1. Upload: workflow XML must go up --binary (keep ASCII bytes).
zowe zos-files upload file-to-uss workflow/rest-inventory.xml \
  /z/andre/rest-inventory.xml --binary --host $HOST

# 2. Register (no variables needed: the rest steps fill them at run time).
zowe zos-workflows create workflow-from-uss-file "REST Inventory" \
  --uss-file /z/andre/rest-inventory.xml --system-name ZOS31 \
  --owner andre --assign-to-owner --host $HOST

# 3. Fast validation gate: forces full template evaluation of every step.
zowe zos-workflows list active-workflow-details --workflow-key <key> \
  --steps-summary-only --host $HOST

# 4. Run the steps in order (rest and setVariable complete near-instantly;
#    the misc column shows HTTP codes and the report step's JOBID).
zowe zos-workflows start workflow-step getInfo     --workflow-key <key> --host $HOST
zowe zos-workflows start workflow-step deriveNames --workflow-key <key> --host $HOST
zowe zos-workflows start workflow-step submitProbe --workflow-key <key> --host $HOST
zowe zos-workflows start workflow-step writeReport --workflow-key <key> --host $HOST

# 5. Read the inventory report straight from the report job's spool.
zowe jobs view all-spool-content <writeReport JOBID> --host $HOST
```

## Interview talking points

- Why did registration fail with `IZUWF8017E` on a mapping as innocent
  as `api_version`? Because `propertyMapping` content is not a name but
  a JSON-path expression evaluated against the response body —
  `["api_version"]` for an object property, `[0]["jobid"]` for an array
  element, `[]` for a whole text/plain body. None of the IBM samples
  shipped on the system uses a rest step, so the XSD plus one IBM
  community blog were the only ground truth.
- Why does the same workflow fail from one terminal and succeed from
  another? The engine derives its self-call target from the client's
  connection URL. An IP-connected client poisons the self-call with an
  address the server certificate cannot vouch for ("No subject
  alternative names matching IP address ... found"). That is an
  environment diagnosis you can only make by reading the automation
  status JSON, not the step table.
- Why not just hardcode the hostname in the XML? `IZUWF8052E` forbids
  `hostname` without `schemeName`, and `IZUWF8053E` makes explicit
  `https` demand username/password elements — and this engine's
  remote-login handshake then 401s credentials that demonstrably work
  against the same endpoint from everywhere else. The lesson: keep
  same-instance rest steps host-less and fix the client connection
  instead.
