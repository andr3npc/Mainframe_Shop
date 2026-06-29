# 04 — ESTAE Recovery Demo

A batch HLASM program that deliberately triggers an abend, recovers in an
ESTAE recovery routine, formats key SDWA fields, and reports what
happened — with both RETRY and PERCOLATE variants.

## Purpose

Demonstrate recovery routine design and SDWA analysis — pairing directly
with deep dump/listing debugging skills — by causing a controlled failure
(e.g., S0C7 data exception) and handling it cleanly.

## Control blocks / services used

- **`ESTAE`** — establish the recovery routine.
- **SDWA** — System Diagnostic Work Area; the recovery routine inspects
  abend code, PSW, registers, and failing instruction address.
- **`SETRP`** — set return parameters to choose RETRY vs PERCOLATE.
- IBM macros: `ESTAE`, `SETRP`, `IHASDWA` (SDWA DSECT).

## Variants

- **RETRY** — recovery routine requests a retry at a clean resume point and
  the program continues.
- **PERCOLATE** — recovery routine reports, then lets the abend percolate
  so the failure is not suppressed.

## HLASM techniques demonstrated

- Establishing and coding an ESTAE recovery exit.
- Mapping and reading the SDWA with `IHASDWA`.
- Driving recovery flow with `SETRP` (RETRY / PERCOLATE / dump options).
- Formatting diagnostic fields for a readable report.
- Standard OS linkage; reentrancy considerations in the recovery path.

## Files

| File | What it is |
|------|------------|
| `src/ESTDEMO.asm` | The program — one CSECT, `AMODE 31 / RMODE ANY`. |
| `jcl/BUILDEST.jcl` | Assemble (`ASMA90`) + bind (`IEWL`) into the load library. |
| `jcl/RUNEST.jcl` | Run both variants: `PARM=RETRY` then `PARM=PERC`. |
| `docs/DESIGN.md` | Full design, register/SDWA notes, edge cases. |

## How the variant is selected

A single program, chosen at run time by the EXEC `PARM`:

| `PARM` | Behaviour | Step result |
|--------|-----------|-------------|
| `RETRY` (or blank) | recover → resume past the error | **RC 0** |
| `PERC` | recover → let the abend stand | **abends S0C7** |

In both cases the recovery routine first WTOs the abend completion code
(`SDWAABCC`), the PSW at the error (`SDWAEC1`), and GPRs 14–15 at the time
of error (`SDWAGRSV`) to JESMSGLG (`ROUTCDE=(11)`).

**Status: built and verified on a real z/OS system** — assembles and links
clean (`ASMA90`/`IEWL` RC 0); the RETRY step ends `COND CODE 0000` and the
PERC step ends `ABEND=S0C7`. See [docs/DESIGN.md](docs/DESIGN.md) for the
captured job log and the debugging lessons.

## Build instructions

1. Upload `src/ESTDEMO.asm` as member `ESTDEMO` in your source PDS and the
   two JCL members into a JCL PDS (the supplied JCL uses `ANDRE.EPE.*` —
   retarget the dataset names to your environment).
2. Submit `jcl/BUILDEST.jcl` — assembles against `ANDRE.EPE.MACLIB`
   (`@ENTER`/`@LEAVE`/`@HEXOUT`) + `SYS1.MACLIB` + `SYS1.MODGEN`
   (`ESTAEX`/`SETRP`/`WTO`/`IHASDWA`) and binds `AMODE 31 / RMODE ANY`
   into the load library.
3. Submit `jcl/RUNEST.jcl`. Expect STEP1 (`RETRY`) to end **RC 0** and
   STEP2 (`PERC`) to **abend S0C7**; both leave the formatted SDWA
   diagnostics in the job log.

> No DCB is involved, so this module is free to load above the 16M line
> (`RMODE ANY`) — unlike the QSAM artifacts (3, 5) which force `RMODE 24`
> so OPEN's 24-bit parameter address resolves.
