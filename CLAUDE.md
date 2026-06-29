# CLAUDE.md — z/OS HLASM Portfolio

This file is loaded automatically at the start of each session so context
carries across sessions. It describes the project, tracks status, and
restates the conventions all code must follow.

## Project

A z/OS HLASM portfolio repository to demonstrate mainframe systems
programming skills to potential employers. Built incrementally over
multiple sessions, one artifact at a time.

### About the author
- Experienced HLASM programmer; currently 100% Assembler + JES support.
- Strongest skill: deep debugging of dumps and assembly listings.
- Tests code on a real z/OS system (work sandbox or IBM Z Xplore).
- Claude cannot assemble or run HLASM in this environment. Claude's job is
  to produce correct source, JCL, and documentation that the author takes
  to the mainframe to build and run.

## Portfolio scope — 5 artifacts

1. **Personal Macro Library** (`01-macro-library/`)
   Curated structured-programming and utility macros: `@ENTER`/`@LEAVE`,
   `@IF`/`@ELSE`/`@ENDIF`, `@DO`/`@ENDDO`, `@HEXOUT`, `@PCALL`.
   Showcases: macro language, conditional assembly, `&SYSNDX`, `GBLA`
   counters for nesting, `MNOTE` diagnostics.

2. **Control Block Walker** (`02-cb-walker/`)
   Batch program that walks PSA → CVT → ASCB → TCB starting at address 0
   and prints key fields from each block. Uses IBM-supplied DSECTs:
   IHAPSA, CVT, IHAASCB, IKJTCB.
   Showcases: control block navigation, DSECT discipline, z/OS internals.

3. **JES2 SYSOUT Scraper** (`03-sysout-scraper/`)
   Batch program that dynamically allocates a SYSOUT dataset via
   `SUBSYS=JES2` (SVC 99), reads it with QSAM, and extracts lines matching
   a pattern.
   Showcases: dynamic allocation, QSAM, JES SSI, real-world sysprog work
   tied to the author's JES background.

4. **ESTAE Recovery Demo** (`04-estae-demo/`)
   Program that deliberately triggers an abend (e.g., S0C7), recovers via
   an ESTAE routine, formats key SDWA fields, and reports what happened.
   Includes both RETRY and PERCOLATE variants.
   Showcases: recovery routines, SDWA analysis, supervisor services; pairs
   directly with the author's debugging strength.

5. **SMF Type-30 Generator + Reporter** (`05-smf30-reporter/`)
   A pair: `MKSMF30` writes synthetic SMF type-30 subtype-5 records, and
   `SMFRPT30` reads them back with QSAM and reports job CPU/elapsed. Uses the
   IBM `IFASMFR (30)` DSECTs (`SMFRCD30`/`SMF30ID`/`SMF30CAS`) and locates
   sections by their header triplets.
   Showcases: SMF record mapping, self-defining sections/triplets, QSAM,
   multi-DSECT addressability — ties to the author's JES/SMF background.

## Status

| # | Artifact              | Status      |
|---|-----------------------|-------------|
| 1 | Personal Macro Library| Complete    |
| 2 | Control Block Walker  | Complete    |
| 3 | JES2 SYSOUT Scraper   | Complete    |
| 4 | ESTAE Recovery Demo   | Complete    |
| 5 | SMF Type-30 Reporter  | Complete    |

Status values: Not started / In progress / Complete.

## Conventions

- z/OS HLASM, AMODE 31, RMODE ANY unless otherwise stated.
- Standard OS linkage: R13 → caller save area, R14 return, R15 entry,
  R1 parm pointer.
- Always use IBM-supplied DSECTs and macros where they exist. Never
  hardcode control block offsets.
- Every source file starts with a prolog comment block:
  Purpose, Inputs, Outputs, Registers used, Registers preserved,
  Dependencies, Sample invocation.
- In macros: `MNOTE` severity 8 for errors, 4 for warnings.
- File extensions on disk: `.asm` for programs, `.mac` for macros, `.jcl`
  for JCL. On z/OS these become PDS members without extensions (noted in
  the top-level README).

## Working approach for future sessions

- One artifact at a time.
- For each artifact, in this order:
  a) `docs/DESIGN.md` — approach, control blocks/services used, register
     conventions, edge cases, what could go wrong.
  b) HLASM source.
  c) JCL to assemble, link-edit, and run.
  d) Update the artifact's README and the Status table above.
- After each chunk of code, briefly explain non-obvious design choices to
  provide interview talking points.
- Push back if a request violates z/OS conventions or would make the
  listing harder to read in a code review.
