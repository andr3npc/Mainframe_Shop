# z/OS HLASM Systems Programming Portfolio

**[GitHub @andr3npc](https://github.com/andr3npc)** &nbsp;·&nbsp; [Talking points](TALKING-POINTS.md) &nbsp;·&nbsp; [Production notes](PRODUCTION-NOTES.md) &nbsp;·&nbsp; [What's inside](#whats-inside)

A collection of IBM z/OS High Level Assembler (HLASM) artifacts that
demonstrate practical mainframe systems programming: macro engineering,
control block navigation, dynamic allocation against JES2, recovery
routine (ESTAE) handling with SDWA analysis, and SMF record mapping —
plus IPCS dump analysis, parm-driven feature-flag routing, and Ansible /
z/OSMF automation.

Everything here is written to z/OS conventions (AMODE 31 / RMODE ANY,
standard OS linkage, IBM-supplied DSECTs and macros) and is meant to be
read like production code in a code review, not just to run.

For a walkthrough of what each artifact demonstrates — the concepts, the
deep technical points, and the debugging war stories behind them — see
[TALKING-POINTS.md](TALKING-POINTS.md). For an honest take on what would
need to change to run any of this in production, and how to test it on a
real system, see [PRODUCTION-NOTES.md](PRODUCTION-NOTES.md).

## What's inside

| # | Artifact | What it demonstrates |
|---|----------|----------------------|
| 1 | [Personal Macro Library](01-macro-library/) | Macro language, conditional assembly, `&SYSNDX`, `GBLA` nesting counters, `MNOTE` diagnostics — structured-programming macros (`@ENTER`/`@LEAVE`, `@IF`/`@ELSE`/`@ENDIF`, `@DO`/`@ENDDO`) plus `@HEXOUT` and `@PCALL`. |
| 2 | [Control Block Walker](02-cb-walker/) | z/OS internals and DSECT discipline — walks PSA → CVT → ASCB → TCB and prints key fields using IHAPSA, CVT, IHAASCB, IKJTCB. |
| 3 | [JES2 SYSOUT Scraper](03-sysout-scraper/) | Dynamic allocation via SVC 99 (`SUBSYS=JES2`), QSAM I/O, and the JES subsystem interface — reads a SYSOUT dataset and extracts matching lines. |
| 4 | [ESTAE Recovery Demo](04-estae-demo/) | Recovery routines and supervisor services — forces an abend (e.g., S0C7), recovers in an ESTAE exit, formats SDWA fields, and reports; RETRY and PERCOLATE variants. |
| 5 | [SMF Type-30 Reporter](05-smf30-reporter/) | SMF record mapping — `MKSMF30` writes synthetic type-30 subtype-5 records, `SMFRPT30` reads them with QSAM and reports job CPU/elapsed, locating sections via the `IFASMFR (30)` header triplets (`SMFRCD30`/`SMF30ID`/`SMF30CAS`). |
| 6 | [IPCS Dump Practice](06-ipcs-dump-practice/) | Dump analysis — `DUMPPGM` builds eye-catcher'd structures and pointer chains, then forces a U0013 dump to analyse with IPCS (`FIND`, `LISTDUMP`, `WHERE`, `CBFORMAT`). |
| 7 | [Ansible Automation](07-ansible-automation/) | DevOps on z/OS — an Ansible playbook drives a HLASM assemble/link through the z/OSMF REST API (submit, poll, fetch output, gate on return code). |
| 8 | [Feature-Flag Routing](08-feature-flag-routing/) | Progressive delivery — `FEATFLAG` selects a LEGACY or NEW path in one load module from the EXEC `PARM`, with no relink to switch. |
| 9 | [z/OSMF VSAM Workflow](09-vsam-workflow/) | Modern z/OS provisioning — a z/OSMF workflow that creates a VSAM KSDS from variable-driven IDCAMS `DEFINE CLUSTER` (fileTemplate JCL), verifies it with TSO-REXX `LISTCAT`, and optionally deletes it; includes the REPRO initial-load JCL. |

## Repository layout

```
mainframe-portfolio/
  README.md              <- this file
  CLAUDE.md              <- project context / status / conventions
  01-macro-library/      src/ examples/ jcl/ docs/ README.md
  02-cb-walker/          src/ jcl/ docs/ README.md
  03-sysout-scraper/     src/ jcl/ docs/ samples/ README.md
  04-estae-demo/         src/ jcl/ docs/ README.md
  05-smf30-reporter/     src/ jcl/ docs/ README.md
  06-ipcs-dump-practice/ src/ jcl/ docs/ README.md
  07-ansible-automation/ playbooks/ jcl/ scripts/ docs/ README.md
  08-feature-flag-routing/ src/ jcl/ docs/ README.md
  09-vsam-workflow/      workflow/ jcl/ docs/ README.md
```

### A note on file extensions

Files on disk use `.asm` (programs), `.mac` (macros), and `.jcl` (JCL) so
they are easy to browse and diff off-platform. **On z/OS these become PDS
members with no extension** — e.g. `src/CBWALK.asm` is uploaded as member
`CBWALK` in a source PDS, and a macro `@HEXOUT.mac` becomes member
`@HEXOUT` in a macro library (SYSLIB) PDS.

## Building and running on z/OS (general)

Each artifact ships its own JCL under `jcl/`, but the shape is the same:

1. **Upload** the source and JCL into PDS(E) datasets (FB 80), e.g.
   `hlq.SOURCE`, `hlq.MACLIB`, `hlq.JCL`. Macros go in a library pointed at
   by the assembler `SYSLIB` DD.

2. **Assemble** with High Level Assembler (program `ASMA90`):
   - `SYSIN` → the source member
   - `SYSLIB` → IBM macro/DSECT libraries (`SYS1.MACLIB`,
     `SYS1.MODGEN`) plus this repo's `hlq.MACLIB` for artifact 1
   - `SYSLIN` → object module output
   - Review `SYSPRINT` — the assembly listing is part of the deliverable.

3. **Link-edit / bind** with the binder (`IEWL`/`HEWL`):
   - `SYSLIN` → object module(s)
   - `SYSLMOD` → load library `hlq.LOAD`
   - AMODE 31 / RMODE ANY as specified per artifact.

4. **Run** via the artifact's execution JCL (a simple `EXEC PGM=` step,
   plus any `STEPLIB`, parameters, and SYSOUT DDs the program needs).

A combined assemble-link-go can use the IBM-supplied `ASMACLG` /
`ASMACL` cataloged procedures; the per-artifact JCL shows the explicit
steps for clarity.

> Programs that touch system control blocks (artifacts 2–4) read live
> z/OS storage and/or use supervisor services. Run them on a system where
> you are authorized to do so (work sandbox or IBM Z Xplore), not on
> production.

## Status

See the status table in [CLAUDE.md](CLAUDE.md). Artifacts are built one at
a time; this README is updated as each is completed.
