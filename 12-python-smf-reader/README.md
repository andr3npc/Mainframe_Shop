# Artifact 12 — Python SMF Type-30 Reader (IBM Open Enterprise SDK for Python)

IBM Open Enterprise SDK for Python (3.13) re-reads `ANDRE.EPE.SMF30` —
the SMF type-30 subtype-5 dataset that artifact 5's HLASM program
`MKSMF30` wrote — and reproduces artifact 5's `SMFRPT30` report from
pure-stdlib Python: JCL stages the VB dataset as `RECFM=U` (keeping
BDWs/RDWs intact), and `smfrpt30.py` walks blocks, records, and
self-defining-section triplets to print a report diff-identical to
`SMFRPT30`'s, plus `--json`.

Verified on a real z/OS 3.1 system (ITSCPLEX / ZOS31, 2026-07-09/10):
`ANDRER30` (`RUNRPT30.jcl`) JOB07111 CC 0000 captured the golden HLASM
report; `ANDRESTG` (`STAGEVB.jcl`) JOB07206 CC 0000 proved the
standalone staging step; `ANDREPY` (`RUNPYRPT.jcl`) JOB07278 CC 0000
(`STAGE` 0000, `PYRPT` 0000) staged and ran the Python report in one
job. The Python report is diff-identical to the golden HLASM report,
and `--json` mode, run directly over SSH, reproduces the same
CPU/elapsed values.

## What it demonstrates

- **IBM Open Enterprise SDK for Python on z/OS** — the host's Python
  3.13 (`/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3`) reads a real
  mainframe dataset directly, no export/convert step outside the
  pipeline itself.
- **BDW/RDW block parsing** — real SMF-dump handling: `_chain()`
  deterministically validates that length-prefixed chunks exactly tile
  a byte range before a block/record framing is accepted, instead of
  guessing from a single heuristic.
- **The RECFM=U staging trick** — `STAGEVB.jcl` overrides IEBGENER's
  `SYSUT1` DCB to `RECFM=U,BLKSIZE=32760` so the VB dataset's BDWs and
  RDWs survive the copy into a USS binary file, working around a `cp`
  with no `-F rdw` and a `cp -B` that silently strips them.
- **EBCDIC + big-endian decode** — job names decoded via `cp1047`,
  every numeric field unpacked with `struct`'s `>` (big-endian) format,
  matching the mainframe's native byte order and code page with pure
  stdlib.
- **Triplet navigation mirroring the HLASM DSECT walk** — the same
  `SMF30IOF`/`SMF30COF` self-defining-section triplets artifact 5's
  `SMFRPT30` walks via DSECT are walked here via empirically pinned
  offsets (header +32/+56 for the triplets, ID+64 and CAS+4/+8 for the
  fields), cross-checked against `MKSMF30.asm`'s literal table.
- **Diffable HLASM↔Python equivalence, plus `--json`** — the report is
  byte-for-byte identical to `SMFRPT30`'s (empty `git diff --no-index`
  after stripping the golden capture's ASA carriage-control column),
  and `--json` adds a machine-readable output the HLASM report has no
  equivalent for — the concrete "why reach for Python here" case.

## Layout

```
12-python-smf-reader/
  src/
    smfrpt30.py       <- stdlib-only parser/reporter: BDW/RDW tiling, triplet nav, report + --json
  tests/
    test_smfrpt30.py  <- 9 unittest cases: golden row, type/subtype skip, report format, JSON, multi-block, truncation RC 8, main() RC 0/4/8
  jcl/
    RUNRPT30.jcl      <- golden capture: runs artifact 5's HLASM SMFRPT30 alone against ANDRE.EPE.SMF30
    STAGEVB.jcl       <- standalone staging: IEBGENER RECFM=U trick, VB dataset -> USS binary file
    RUNPYRPT.jcl      <- stage + Python report in one job; duplicates STAGEVB.jcl's STAGE step because JCL (as used in this repo) has no include mechanism
  docs/
    DESIGN.md         <- offset-discovery evidence, RECFM=U staging rationale, verified-run diff proof, error archaeology
```

## Running it (Zowe CLI)

```bash
# Host: zos31.pok.stglabs.ibm.com — set once as $HOST and reused across
# every command below.
HOST=zos31.pok.stglabs.ibm.com

# 1. Submit the combined stage + Python report job (STAGE re-stages the
#    dataset, PYRPT runs smfrpt30.py against it and prints the report
#    to spool).
zowe jobs submit local-file jcl/RUNPYRPT.jcl --wait-for-output --host $HOST

# 2. View the report on the PYRPT step's STDOUT spool.
zowe jobs view all-spool-content <PYRPT JOBID> --host $HOST

# 3. Optional: run the 9-test unittest suite directly on the host.
zowe uss issue ssh \
  "/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 -m unittest discover -s /z/andre/a12/tests -v" \
  --host $HOST

# 4. Optional: JSON mode over SSH instead of through spool.
zowe uss issue ssh \
  "/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin --json" \
  --host $HOST
```

## Interview talking points

- Why replace "looks like a BDW" heuristics with tiling validation?
  Two scalar heuristics — "outer chunk length > 316" then "first chunk
  length == len(data)" — each misclassified real inputs (a short
  truncated file; a legitimate multi-block file, whose first block is
  shorter than the whole file by design) because they tested one
  number instead of the whole byte layout. `_chain()` instead demands
  every length-prefixed chunk exactly tile its byte range with zero
  slack and zero overrun before a framing is accepted, and `_records()`
  only falls back from BDW+RDW to bare RDW when the *outer* tiling is
  provably impossible — never as a silent fallback from a
  partially-consistent read.
- Why does `struct.unpack` never escape `main()` as a raw exception?
  An early version let a short-but-plausible record (right type and
  subtype, but too short for the fields read next) raise `struct.error`
  straight out of `main()` — a Python traceback where a mainframe
  report should print RC 8. Every `struct.unpack` that depends on an
  unvalidated length now sits behind an explicit bounds check that
  raises a named `ParseError` first, and the test suite asserts RC 8
  (not an unhandled exception) on malformed input.
- Why read a VB dataset as `RECFM=U` just to get it into USS? Because
  the two obvious copy paths lose the descriptor words this parser
  needs: this system's `cp` has no `-F rdw`, and `cp -B` silently
  strips the RDWs (confirmed by a 936-byte copy where 952 was
  expected). Overriding the `SYSUT1` DCB to `RECFM=U,BLKSIZE=32760`
  makes IEBGENER treat the dataset as raw undefined-format blocks, so
  the BDW and RDWs come across byte-for-byte into the USS `PATH=`
  target — exactly the bytes `_chain()` needs to validate.
