# Design — z/OSMF Liberty Server Dump Workflow

## Problem

When the z/OSMF server misbehaves (hangs, slow REST responses, leaking
heap), IBM support asks for a Liberty server dump. Capturing one by
hand means knowing the right modify command, the right started task,
and where Liberty writes its output. This workflow packages that
procedure so any operator can run it from the z/OSMF UI (or Zowe CLI)
and gets a verified result, not a "probably worked".

## Shape: verify → act → verify

| # | Step | Type | Judged by | What it does |
|---|------|------|-----------|--------------|
| 1 | `verifyLiberty` | shell-JCL | RC | `ls` the Liberty `server` binary at `${instance-WLP_BIN}`; exit 1 if absent |
| 2 | `generateDump` | shell-JCL | RC | `/usr/sbin/operator "F IZUSVR1,JAVADUMP"` — MVS modify against the z/OSMF started task |
| 3 | `verifyDump` | shell-JCL | RC | glob `zosmfServer.dump-*.zip` in `/global/zosmf/ZOS31/data/logs/zosmfServer`; exit 1 if none |

Steps are chained with `prereqStep`, so the workflow engine enforces
the order; `autoEnable` lets each step arm itself as soon as its
prerequisite completes.

## Schema rules this workflow leans on

These were learned the hard way (validator error codes in brackets);
the workflow XML is shaped by them:

- A step's action must be exactly one of `template` / `rest` /
  `setVariable`. There is **no `rexx` or `shell` element** in the
  schema — a script step is an `inlineTemplate` with the right
  `submitAs` [`cvc-complex-type.2.4.a`].
- `submitAs` is a **child element of `template`**, not an attribute of
  `inlineTemplate` [`cvc-complex-type.3.2.2`]. Valid values: `JCL`,
  `TSO-REXX`, `shell-JCL`.
- `successPattern` is **required for TSO-REXX** [IZUWF0302E] and
  **forbidden for shell-JCL** [IZUWF0303E]. shell-JCL is wrapped as a
  BPXBATCH job and judged by return code, which is why every script
  here ends in an explicit `exit` status on its failure path.
- With `substitution="true"`, z/OSMF parses **every** `${...}` in the
  template as a workflow variable reference — shell forms like
  `${VAR:-default}`, `${#VAR}` or `${VAR/a/b}` crash template
  evaluation [IZUWF0084E]. The scripts therefore stick to plain
  `$shellvar`, `$(...)`, and real `${instance-NAME}` references only.
- Instance variables must be referenced as `${instance-NAME}`; a bare
  `${NAME}` is silently left untouched and the shell sees the literal
  text.

## Variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `WLP_BIN` | step 1 | Path to Liberty's `bin/` — existence check target |
| `WLP_USER_DIR` | (informational) | Server configuration root, shown to the operator |
| `DUMP_ARCHIVE` | (informational) | Historical target path, echoed in instructions |
| `DUMP_INCLUDE` | (informational) | Requested dump types, echoed by step 2 |

Only `WLP_BIN` steers execution. `DUMP_ARCHIVE` and `DUMP_INCLUDE`
document intent and surface in the step instructions/echo output; the
javadump itself is produced by the server wherever Liberty logs
(`/global/zosmf/ZOS31/data/logs/zosmfServer`), which is exactly what
step 3 verifies. A `<default>` only pre-fills the z/OSMF UI prompt —
headless (CLI/REST) registration must pass `--variables`, or every
`${instance-NAME}` passes through literally.

## Why an operator command and not `server dump`?

`wlp/bin/server dump zosmfServer` must run as a user who owns the
server process and its output directories (`IZUSVR`). Issuing
`F IZUSVR1,JAVADUMP` instead asks the *running server* to dump itself:
the workflow user needs console-command authority, not filesystem
access to IZUSVR's directories, and the output appears in the standard
Liberty log location with a timestamped name
(`zosmfServer.dump-YY.MM.DD_HH.MM.SS.zip`) that the verify step can
glob for.

## Encoding

The workflow XML must be uploaded to USS with `--binary`. A normal
`zowe zos-files upload file-to-uss` transcodes ASCII→EBCDIC (IBM-1047),
and z/OSMF then reads the file as ASCII: byte `0x4C` (EBCDIC `<`)
looks like `L` and the parser fails with `IZUWF0120E ... "Content is
not allowed in prolog"`. After a binary upload the first bytes are
`3C 3F 78 6D 6C` (`<?xml`) as required.

## Evidence of the verified run (ZOS31, 2026-07-07)

```
name          state    stepNumber misc
verifyLiberty Complete 1          JOB05976
generateDump  Complete 2          JOB05977
verifyDump    Complete 3          JOB05978
```

From JOB05978's spool:

```
SUCCESS: Latest dump file found:
-rw-rw----  1 IZUSVR IZUADMIN 19558503 Jul  7 10:48
/global/zosmf/ZOS31/data/logs/zosmfServer/zosmfServer.dump-26.07.07_14.48.14.zip
```

Because step 3 exits 1 when the glob is empty, "Complete" is a proof
the dump exists — the workflow cannot end green without a fresh
archive on disk.
