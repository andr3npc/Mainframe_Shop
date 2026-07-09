# Artifact 12: Python SMF Type-30 Reader — Design Spec

**Date:** 2026-07-09
**Status:** Approved by user (approach A: pure stdlib + record-preserving stage)

## Goal

A Python-on-z/OS artifact (`12-python-smf-reader/`) proving the portfolio's SMF
record-mapping story in a second language: **IBM Open Enterprise SDK for Python
reads the same `ANDRE.EPE.SMF30` dataset that artifact 5's HLASM `MKSMF30`
wrote, and reproduces `SMFRPT30`'s report line-for-line** — with the two
outputs proven equivalent by `diff`. A `--json` flag adds the one thing the
HLASM version cannot do cheaply.

## Environment facts (verified on ZOS31, 2026-07-09)

- IBM Open Enterprise SDK for Python **3.13.0** at
  `/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3` (pip present).
- ZOAU 1.3.5 at `/apps/zoautil` — its `zoautil_py` wheel is tagged **cp310**;
  compatibility with 3.13 unknown. **Not a dependency of this design** (road
  not taken; may be noted in docs).
- `ANDRE.EPE.SMF30` exists, RECFM=VB, was HSM-migrated and **recalled by the
  2026-07-09 smoke test** (recall is automatic on first access; documented).
- **Smoke test passed on ZOS31 (2026-07-09):** Python 3.13.0 read a 936-byte
  `cp -B` staging copy and verified record type 30, subtype 5, SID `ZS31`
  (EBCDIC via cp1047) at the expected offsets — data, interpreter, and
  decode approach all confirmed live.
- Record content: synthetic SMF type 30 subtype 5 records; report navigates
  the ID section (`SMF30IOF/ILN/ION` triplet) and CPU/accounting section
  (`SMF30COF/CLN/CON` triplet). Field map lives in
  `05-smf30-reporter/docs/DESIGN.md` and the `MKSMF30`/`SMFRPT30` sources —
  the implementation must read offsets from there, not invent them.

## Components

### `12-python-smf-reader/src/smfrpt30.py`
Single-file, **stdlib only** (argparse, struct, codecs/str.decode, json, sys).

1. Input: path to a USS binary staging file containing the dataset's raw
   **blocks with BDW/RDWs intact**, produced by the JCL stage step reading the
   VB dataset as RECFM=U (see RUNPYRPT.jcl below). Smoke-tested findings
   (2026-07-09): this system's `cp` rejects `-F rdw` (usage error, even
   `/bin/cp`); ZOAU `dcp -B` hung after a TMPDIR fix; plain `cp -B` works but
   strips RDWs. The RECFM=U JCL trick is the reliable, JCL-native answer —
   and parsing BDW→RDW→record in Python is truer to real SMF dump handling.
2. Record walk: read 4-byte BDW (big-endian halfword block length), walk the
   RDW-prefixed records inside each block, slice each record, skip records
   that are not type 30 subtype 5 (count them).
3. Section navigation: locate ID and CPU sections via their triplets
   (offset/length/count relative to the record start, as in SMFRPT30).
4. Field decode: EBCDIC text via cp1047, binary counts via `struct`
   big-endian; time/CPU field conversions replicated from SMFRPT30's logic.
5. Default output: **byte-identical** to SMFRPT30's spool report (same
   heading, same one-line-per-job format, same totals if any).
6. `--json`: same data as a JSON array to stdout instead of the report.
7. Exit codes (mirrors the artifact-5 RC discipline): 0 = report written;
   4 = readable input but zero subtype-5 records; 8 = missing/empty/corrupt
   input (short record, truncated triplet) with a diagnostic on stderr.

### `12-python-smf-reader/jcl/RUNPYRPT.jcl`
BPXBATCH job, RC-gated like every other artifact's JCL:
- STEP1 (IEBGENER): `SYSUT1 DD DSN=ANDRE.EPE.SMF30,DISP=SHR,DCB=(RECFM=U,BLKSIZE=32760)`
  → `SYSUT2 DD PATH='/z/andre/smf30.bin',...,FILEDATA=BINARY` — reading VB as
  RECFM=U yields raw blocks including BDW/RDWs (classic sysprog trick).
- STEP2 runs `/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 <script> <stage-file>`
  with stdout to a SYSOUT-visible file/DD so the report lands in the spool.

### Docs
- `docs/DESIGN.md` — record layout as parsed from Python (offsets table
  cross-referenced to the HLASM DSECT names), EBCDIC/struct notes, error
  archaeology from the build, evidence of the verified run.
- `README.md` — artifact-10/11 structure: summary, "Verified on ZOS31 ...",
  What it demonstrates, Layout, Running it (Zowe CLI), Interview talking
  points.
- Top-level `README.md` row 12 + layout line; `CLAUDE.md` scope 11 → 12,
  item 12, status row.

## Verification (the artifact's core claim)

1. Run HLASM `SMFRPT30` (artifact 5's `RUNSMF.jcl` report step or equivalent)
   against `ANDRE.EPE.SMF30`; capture spool.
2. Run `RUNPYRPT.jcl`; capture spool.
3. `diff` the two report bodies — **zero differences** is the success
   criterion (modulo JES banner lines outside the report body).
4. `--json` output parses with `json.loads` and contains the same job rows.

## Error handling

- Migrated dataset: first stage step may run long during HSM recall — the
  JCL step must tolerate it (no timeout assumptions); documented.
- Empty/absent dataset: rerun artifact 5's `MKSMF30` build JCL to regenerate
  records (documented as the reset path), rather than hand-crafting data.
- Truncated/garbage records: RC 8 + stderr diagnostic naming the record
  number and expected vs available length.

## Success criteria

1. `smfrpt30.py` runs on ZOS31 under the IBM Python 3.13 and exits 0.
2. Python report is diff-identical to the HLASM SMFRPT30 report for the same
   dataset.
3. `--json` emits valid JSON with the same rows.
4. All repo conventions followed (artifact layout, READMEs, CLAUDE.md,
   evidence in DESIGN.md).

## Non-goals

- No pip packages, no ZOAU Python API dependency, no venv.
- No reading of live SYS1.MANx / SMF logstreams — synthetic artifact-5 data
  only (lab-safe, self-contained story).
- No Windows-side execution of the parser (it runs where the data lives).
