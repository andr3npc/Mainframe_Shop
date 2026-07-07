# Artifact 10 — z/OSMF Liberty Server Dump Workflow

A z/OSMF **Workflow** that captures diagnostics from the z/OSMF Liberty
server itself: a shell step verifies the Liberty installation, a second
step triggers a javadump against the `IZUSVR1` started task via an MVS
modify command, and a third step proves the dump archive actually
landed on disk — failing the workflow if it did not.

Verified on a real z/OS 3.1 system (z/OSMF workflow engine, ITSCPLEX /
ZOS31): all three steps ran as JES jobs (`JOB05976`–`JOB05978`) to
Complete, and the verify step found the fresh 19.5 MB archive
`zosmfServer.dump-26.07.07_14.48.14.zip` in
`/global/zosmf/ZOS31/data/logs/zosmfServer`.

## What it demonstrates

- **shell-JCL workflow steps** — the third of the three `submitAs`
  types (`JCL`, `TSO-REXX`, `shell-JCL`). Each inline shell script is
  wrapped by z/OSMF into a BPXBATCH job and judged **by return code**;
  `successPattern` is *forbidden* here (`IZUWF0303E`), unlike TSO-REXX
  steps where it is required.
- **Step sequencing with `prereqStep`** — verify → act → verify. The
  dump step cannot run until the install check passes, and the final
  check cannot run until the dump was requested.
- **Defensive verification** — both check steps end in an explicit
  `exit 1` on the failure path, so "step Complete" is a real assertion
  (the last step greps the log directory for a `zosmfServer.dump-*.zip`
  and fails if none exists), not just "the script ran".
- **Operating on the operator's side of z/OS** — the dump is triggered
  with `/usr/sbin/operator "F IZUSVR1,JAVADUMP"`, i.e. an MVS modify
  command issued from a USS shell against the z/OSMF server's own
  started task — the workflow diagnoses the very server that runs it.
- **Encoding discipline** — the workflow XML is uploaded `--binary` so
  z/OSMF reads the ASCII bytes it expects (a plain upload transcodes to
  EBCDIC and the parser dies with "Content is not allowed in prolog").

## Layout

```
10-liberty-dump-workflow/
  workflow/
    liberty_dump.xml   <- workflow definition (3 shell-JCL steps, 4 variables)
  docs/
    DESIGN.md          <- design notes and schema/substitution rules
```

## Running it (Zowe CLI)

```bash
# 1. Upload: workflow XML must go up --binary (keep ASCII bytes).
zowe zos-files upload file-to-uss workflow/liberty_dump.xml \
  /z/andre/workflows/liberty_dump.xml --binary

# 2. Register. Supply variable values here: <default> only pre-fills
#    the UI prompt, it does NOT resolve headless substitution.
zowe zos-workflows create workflow-from-uss-file "Liberty Server Dump" \
  --uss-file /z/andre/workflows/liberty_dump.xml --system-name ZOS31 \
  --owner andre --assign-to-owner \
  --variables "WLP_USER_DIR=/global/zosmf/ZOS31/configuration,WLP_BIN=/usr/lpp/zosmf/liberty/bin,DUMP_ARCHIVE=/z/andre/zosmf_dump.zip,DUMP_INCLUDE=thread,heap"

# 3. Fast validation gate: forces full template evaluation of every
#    step without running anything.
zowe zos-workflows list active-workflow-details --workflow-key <key> --steps-summary-only

# 4. Run the steps in order (shell-JCL completes quickly; the misc
#    column shows each step's JOBID).
zowe zos-workflows start workflow-step verifyLiberty --workflow-key <key>
zowe zos-workflows start workflow-step generateDump  --workflow-key <key>
zowe zos-workflows start workflow-step verifyDump    --workflow-key <key>

# 5. Read the evidence straight from the verify job's spool.
zowe jobs view all-spool-content <verifyDump JOBID>
```

## Interview talking points

- Why is there no `successPattern` on these steps, when artifact 9's
  REXX step needed one? Because the success contract differs by step
  type: TSO-REXX runs synchronously in a TSO address space and z/OSMF
  can only judge it by matching stdout, while shell-JCL is wrapped as a
  BPXBATCH job and judged by return code — so the scripts here encode
  success as `exit` status, not as a printed sentinel.
- Why trigger the dump with an operator modify command instead of
  running `wlp/bin/server dump` directly? The server runs under the
  `IZUSVR` user; the modify command asks the running server to dump
  itself, so the workflow user needs console command access rather
  than write access to the server's own directories — and the output
  lands where Liberty always logs, which the verify step then checks.
- What happens if the dump never appears? `verifyDump` lists
  `zosmfServer.dump-*.zip` in the Liberty log directory and exits 1 if
  the glob comes back empty, so the workflow step goes to Failed
  instead of silently reporting success.
