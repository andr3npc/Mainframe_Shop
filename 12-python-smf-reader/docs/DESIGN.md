# Design — Python SMF Type-30 Reader

## Record layout (empirically pinned on ZOS31, 2026-07-09)

`ANDRE.EPE.SMF30` was staged to USS as `/z/andre/smf30.bin` (see "Staging:
why RECFM=U" below) and its raw bytes decoded with a scratch discovery
script (`tmp/artifact12/discover.py`, not committed — findings recorded
here).

**BDW/RDW mode found:** `BDW+RDW`. The staged file is 952 bytes = one
block: a 4-byte BDW (`03 B8` = 952) followed by three 316-byte records,
each itself starting with its own 4-byte RDW (`01 3C` = 316). This
matches the artifact 5 generator's `RECLEN = 228 (header) + 72 (ID) + 16
(CAS) = 316`, RDW included.

Field offsets below are given two ways: **header-relative** for the two
triplets (offset from the start of the 316-byte logical record, RDW
included — this is how `SMF30IOF`/`SMF30COF` are defined in `IFASMFR
(30)`), and **section-relative** for the three arithmetic-pinned fields
(offset from the start of the section the triplet points to).

**Scope caveat:** these offsets are pinned to *this* dataset — artifact
5's `MKSMF30` builds deliberately shortened ID (72-byte) and CAS
(16-byte) sections, so the table below is not a general `IFASMFR (30)`
layout reference; real SMF30 data would need the same empirical
re-derivation.

| Field | Offset | Evidence |
|-------|--------|----------|
| `SMF30IOF` (ID section triplet: offset/len/count) | header +32 | Triplet bytes at record offset 32 decode as `(228, 72, 1)` — offset 228, length 72, count 1 — the exact ID-section geometry baked into `MKSMF30.asm`: the section starts right after the header (`RHDRLEN=228`, hence offset 228) and its own length is `RIDLEN=72`. Found identically in all 3 records. |
| `SMF30COF` (processor/CAS section triplet: offset/len/count) | header +56 | Triplet bytes at record offset 56 decode as `(300, 16, 1)` — offset 300 (= 228+72), length 16, count 1 — the exact CAS-section geometry (`RCASLEN=16`). Found identically in all 3 records. |
| `SMF30RST` (reader-in time, hundredths) | ID section +64 (record offset 228+64=292) | For every job, `SMF30TME − SMF30RST` must equal the golden elapsed time (ANDREJ1 500.00s=50000, PAYROLL 3600.00s=360000, BACKUP 120.00s=12000). Searching ID-section offsets 0..67 for a fullword equal to `TME − golden_elapsed` produced exactly **one** candidate offset — 64 — consistent across all three records. Independently confirmed against `MKSMF30.asm`'s literal table: ANDREJ1 `TBRST=F'3240000'` = `TME 3290000 − 50000`, matching exactly. |
| `SMF30CPT` (TCB CPU time, hundredths) | CAS section +4 (record offset 300+4=304) | Of the four CAS fullwords (offsets 0/4/8/12 — bytes 0 and 12 are always 0 in this sample), offsets +4 and +8 sum to the golden CPU time for every job (ANDREJ1 130.23s=13023, PAYROLL 2515.00s=251500, BACKUP 100.00s=10000). `MKSMF30.asm` pins which is which: `TBCPT` (TCB CPU) is written before `TBCPS` (SRB CPU) into `SMF30CPT`/`SMF30CPS`, and the +4 word matches `TBCPT`'s literal value exactly for all three jobs (e.g. ANDREJ1 `TBCPT=F'12345'` = CAS+4 value 12345). |
| `SMF30CPS` (SRB CPU time, hundredths) | CAS section +8 (record offset 300+8=308) | Same evidence as above; the +8 word matches `TBCPS`'s literal value exactly for all three jobs (e.g. ANDREJ1 `TBCPS=F'678'` = CAS+8 value 678). |

Discovery script output (verbatim, run on ZOS31 via
`/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3`):

```
file bytes: 952
mode: BDW+RDW records: 3 lengths: [316, 316, 316]
record 0 triplet at header offset 32 -> (228, 72, 1)
record 0 triplet at header offset 56 -> (300, 16, 1)
record 1 triplet at header offset 32 -> (228, 72, 1)
record 1 triplet at header offset 56 -> (300, 16, 1)
record 2 triplet at header offset 32 -> (228, 72, 1)
record 2 triplet at header offset 56 -> (300, 16, 1)
ANDREJ1 TME 3290000 RST candidates at ID+ [64]
PAYROLL TME 3960000 RST candidates at ID+ [64]
BACKUP TME 3972000 RST candidates at ID+ [64]
ANDREJ1 CAS words [0, 12345, 678, 0] need sum 13023
PAYROLL CAS words [0, 250000, 1500, 0] need sum 251500
BACKUP CAS words [0, 9999, 1, 0] need sum 10000
```

**Authoritative offsets for Task 3** (record-relative, RDW included in
the record):

| Symbol | Value |
|--------|-------|
| `IOF_AT` (header offset of `SMF30IOF` triplet) | 32 |
| `COF_AT` (header offset of `SMF30COF` triplet) | 56 |
| `RST_AT` (`SMF30RST`, ID-section-relative) | 64 |
| `CPT_AT` (`SMF30CPT`, CAS-section-relative) | 4 |
| `CPS_AT` (`SMF30CPS`, CAS-section-relative) | 8 |

## Staging: why RECFM=U

`ANDRE.EPE.SMF30` is `RECFM=VB`. To get the raw bytes — including block
descriptor words (BDW) and record descriptor words (RDW) — into USS
intact, `STAGEVB.jcl` overrides the DCB on `SYSUT1` to `RECFM=U,
BLKSIZE=32760`. A `RECFM=U` override on the input DD makes IEBGENER read
the dataset as undefined-format raw blocks: it does not strip descriptor
words the way a normal VB read (or a plain USS `cp`) would, because
`RECFM=U` records are, by definition, whatever bytes are in the block —
BDW and all.

This matters because the two obvious USS copy paths don't preserve the
descriptor words on this system:

- `cp -F rdw` is not available — this system's `cp` doesn't implement
  that flag.
- `cp -B` (binary copy of a variable-length dataset) strips the RDWs;
  the earlier smoke test's `cp -B` copy measured 936 bytes = 3×312 (316
  minus the 4-byte RDW, three times) — confirming the RDWs were gone.

So `RECFM=U` on the `SYSUT1` override plus `FILEDATA=BINARY` on the USS
target (`SYSUT2`) is the mechanism that lands a byte-for-byte copy of
the dataset's physical blocks — BDW, RDWs, and record payloads all
intact — which the discovery script (and, later, the Python parser in
Task 3) can decode without any z/OS-side reformatting.

## Verified staging run (ZOS31)

`STAGEVB.jcl` submitted as `ANDRESTG`, JOB07206, `CC 0000`.

```
$     03  B8  00  00  01  3C  00  00  00  1E  00  32

-rw-r-----   1 ANDRE    SYS1         952 Jul  9 22:23 /z/andre/smf30.bin
```

First halfword `03 B8` = 952 = block length (3×316+4), confirming a BDW
is present (not RDW-first): a bare first record would show `01 3C` (316)
in that position. Bytes 4-5 `01 3C` = 316 = the first record's RDW
length, confirming `BDW+RDW` mode exactly as expected.

## Evidence of the verified run (ZOS31, 2026-07-10)

End-to-end equivalence proof: the HLASM `SMFRPT30` report and the Python
`smfrpt30.py` report are diff-identical, byte for byte (modulo the ASA
carriage-control column that only the HLASM report has).

| Job | JOBID | Step | RC | Purpose |
|-----|-------|------|----|---------|
| `RUNRPT30` (`RUNRPT30.jcl`) | JOB07111 | `RPT` | CC 0000 | Golden report capture (HLASM `SMFRPT30` against `ANDRE.EPE.SMF30`) |
| `ANDRESTG` (`STAGEVB.jcl`) | JOB07206 | `STAGE` | CC 0000 | Stage `ANDRE.EPE.SMF30` to `/z/andre/smf30.bin`, BDW/RDW intact (952 bytes) |
| `ANDREPY` (`RUNPYRPT.jcl`) | JOB07278 | `STAGE` | CC 0000 | Re-stage to `/z/andre/smf30.bin` in the same job as the report run |
| `ANDREPY` (`RUNPYRPT.jcl`) | JOB07278 | `PYRPT` | CC 0000 | `BPXBATCH` runs `python3 /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin`, report to `STDOUT` spool |

Python report pulled from JOB07278's `PYRPT` `STDOUT` spool DD (id 103,
5 records) and written to `tmp/artifact12/python-report.txt` (UTF-8, no
BOM, CRLF). The golden capture (`tmp/artifact12/golden-report.txt`, 5
lines, CRLF) has column 1 of every line stripped as the ASA
carriage-control character — the HLASM `RPTDD` is a print-format SYSOUT
DD with a carriage-control column that plain `STDOUT` from Python does
not have — producing `tmp/artifact12/golden-noasa.txt`. Diffed:

```
git diff --no-index tmp/artifact12/golden-noasa.txt tmp/artifact12/python-report.txt
```

Result: **empty diff, exit 0.** No output at all — the two reports are
identical byte for byte.

JSON mode, run directly over SSH rather than through spool (`zowe uss
issue ssh`):

```
python3 /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin --json
```

```
[{"job": "ANDREJ1", "cpu_sec": 130.23, "elapsed_sec": 500.0}, {"job": "PAYROLL", "cpu_sec": 2515.0, "elapsed_sec": 3600.0}, {"job": "BACKUP", "cpu_sec": 100.0, "elapsed_sec": 120.0}]
```

`cpu_sec` values (130.23 / 2515.0 / 100.0) match the golden report's CPU
column exactly, confirming the JSON path shares the same parse/compute
logic as the text report path.

The 9-test unit suite (`tests/test_smfrpt30.py`) continues to pass 9/9
on the host's Python 3.13 (`/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3
-m pytest`), unchanged from the state recorded after commit `b56fb92`.

## Error archaeology

Honest record of real errors hit across Tasks 1-4, and what actually
fixed each one — not a cleaned-up narrative.

| # | What went wrong | Root cause | Fix |
|---|---|---|---|
| a | The first golden-report capture, saved from a PowerShell terminal with `Get-Content ... -Encoding utf8`, silently gained a 3-byte UTF-8 BOM at the start of the file, which would have made every downstream diff and offset calculation wrong. | Windows PowerShell 5.1's `-Encoding utf8` always emits a BOM; there is no flag to suppress it. | Rewrote the file from raw bytes with `[System.IO.File]::WriteAllBytes` (and later `WriteAllLines` with `New-Object System.Text.UTF8Encoding($false)`), never PowerShell 5.1's built-in `-Encoding utf8`. |
| b | Two successive record-framing heuristics misclassified real inputs: first, "outer chunk length > 316" to detect a BDW misclassified the truncation test (a short file whose first halfword happened to be a small, valid-looking length); its replacement, "first chunk length == len(data)" to detect a single-block BDW, in turn misclassified legitimate multi-block files (whose first block is shorter than the whole file by design). | Both heuristics tried to distinguish BDW-framed from bare-RDW-framed input from a single scalar comparison instead of validating the whole byte layout. | Replaced both with deterministic validate-by-tiling: `_chain()` walks length-prefixed chunks and only accepts a framing if the chunks exactly tile the byte range with no slack and no overrun; `_records()` commits to BDW+RDW only when the *outer* tiling (block-level) succeeds first, then requires the *inner* tiling (RDW-level) to succeed within each block, raising rather than silently falling back to bare-RDW if the inner tiling fails. |
| c | `struct.unpack` raised an uncaught `struct.error` (not `ParseError`) out of `main()` for short-but-plausible records — ones that passed the `RTY=30`/`STP=5` type/subtype check but were shorter than 64 bytes, too short to hold the fields the parser reads next. | The parser assumed any record that matched type/subtype was long enough to hold every field it goes on to read, with no explicit bounds check before the reads. | Added explicit bounds checks (`ParseError` raised by name, e.g. "record shorter than SMF header", "record too short for triplet headers", "ID section too short ... for SMF30RST") ahead of every `struct.unpack` that depends on a length not yet validated, plus `main()`-level tests asserting RC 8 (not an unhandled exception) on short/malformed input. |
| d | Nothing new. The plan flagged a risk that `BPXBATCH`'s `STDPARM` two-line continuation (`SH ... python3` on one line, the script path and argument wrapped to a second line) might arrive at the shell mangled. `RUNPYRPT.jcl` was submitted with the plan's exact two-line `STDPARM` unchanged, and `PYRPT` (JOB07278) completed with `COND CODE 0000` and produced the correct 5-line report on the first submission — no mangling observed, no single-line fallback needed. | N/A | N/A — recorded here only because the plan asked to note whatever was actually required; in this run, nothing extra was required. |
