# Artifact 9 — z/OSMF VSAM Provisioning Workflow

A z/OSMF **Workflow** that provisions a VSAM KSDS cluster end to end:
IDCAMS `DEFINE CLUSTER` driven by workflow variables, a TSO/REXX
`LISTCAT` verification step, and an optional IDCAMS `DELETE` cleanup
step. Plus the JCL used to load and read back the new cluster.

Verified on a real z/OS 3.1 system (z/OSMF workflow engine, ITSCPLEX):
the registered workflow's `define-ksds` step ran as a JES job and
created `ANDRE.EPE.KSDS1` (+ `.DATA` / `.INDEX` components), and the
load job REPRO'd 10 records and read them back through the index
(`IDC0005I NUMBER OF RECORDS PROCESSED WAS 10`, max condition code 0).

## What it demonstrates

- **z/OSMF workflow authoring** — the real schema, not the folklore:
  a step's action must be exactly one of `template` / `rest` /
  `setVariable`; there is no `rexx` or `shell` element.
- **Template-based steps** — the DEFINE JCL lives in a separate
  template file referenced by `fileTemplate` (the same structure IBM's
  `adduser` sample workflows use), so the JCL can be maintained without
  touching the workflow XML.
- **Variable substitution** — seven instance variables
  (`VSAM_DSN`, `KEY_LENGTH`, `KEY_OFFSET`, `AVG_RECLEN`, `MAX_RECLEN`,
  `PRIMARY_CYL`, `SECONDARY_CYL`) referenced as `${instance-NAME}`
  inside both the JCL template and the inline REXX.
- **Mixed step types** — a JCL step judged by return code, a TSO-REXX
  step judged by a `successPattern` regex against its output, and an
  optional step the operator can skip.
- **VSAM fundamentals** — KSDS geometry (`KEYS`, `RECORDSIZE`, `CYL`,
  `SHAREOPTIONS`, `FREESPACE`), explicit DATA/INDEX component naming,
  and the initial-load rule that REPRO input must arrive in ascending
  key order.

## Layout

```
09-vsam-workflow/
  workflow/
    vsam-create.xml       <- workflow definition (3 steps, 7 variables)
    vsam-define.template  <- IDCAMS DEFINE CLUSTER JCL (fileTemplate target)
  jcl/
    LOADKSDS.jcl          <- REPRO initial load + PRINT read-back
  docs/
    DESIGN.md             <- design notes and hard-won schema/encoding rules
```

## Running it (Zowe CLI)

```bash
# 1. Upload: the XML must go up --binary (keep ASCII bytes for z/OSMF);
#    the JCL template goes up as text (EBCDIC), matching how z/OSMF
#    reads fileTemplate targets.
zowe zos-files upload file-to-uss workflow/vsam-create.xml /z/andre/vsam-create.xml --binary
zowe zos-files upload file-to-uss workflow/vsam-define.template /z/andre/vsam-define.template

# 2. Register. Supply variable values here: <default> only pre-fills the
#    UI prompt, it does NOT resolve headless substitution.
zowe zos-workflows create workflow-from-uss-file "VSAM-CREATE" \
  --uss-file /z/andre/vsam-create.xml --system-name ZOS31 \
  --owner andre --assign-to-owner \
  --variables "VSAM_DSN=ANDRE.EPE.KSDS1,KEY_LENGTH=8,KEY_OFFSET=0,AVG_RECLEN=80,MAX_RECLEN=80,PRIMARY_CYL=1,SECONDARY_CYL=1"

# 3. Fast validation gate: forces full template evaluation of every step
#    without running anything.
zowe zos-workflows list active-workflow-details --workflow-key <key> --steps-summary-only

# 4. Perform the define step (JCL steps complete quickly; the misc
#    column shows the JOBID).
zowe zos-workflows start workflow-step define-ksds --workflow-key <key>

# 5. Load sample data.
zowe jobs submit local-file jcl/LOADKSDS.jcl --wait-for-output
```

The TSO-REXX verify step queues slowly when started from the CLI on a
busy shared LPAR; performing it from the z/OSMF web UI runs it in the
user's ISPF-gateway TSO session with immediate output.

## Interview talking points

- Why `${instance-VSAM_DSN}` and not `${VSAM_DSN}`? The `instance-`
  prefix is the substitution namespace; a bare `${NAME}` is silently
  left untouched and the script sees the literal text.
- Why is `successPattern` present on the REXX step but absent on the
  JCL steps? TSO-REXX runs synchronously in a TSO address space, so
  z/OSMF judges success by matching stdout; JCL (and shell-JCL) steps
  are judged by job return code, and `successPattern` is rejected.
- Why upload the XML `--binary` but the template as text? See
  docs/DESIGN.md — the encoding matrix (ASCII XML vs EBCDIC template)
  cost real debugging time and is exactly the kind of detail that
  breaks automation silently.
