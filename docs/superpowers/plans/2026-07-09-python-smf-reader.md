# Artifact 12: Python SMF Type-30 Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify on ZOS31 a stdlib-only Python reader (`12-python-smf-reader/`) that parses the BDW/RDW blocks of `ANDRE.EPE.SMF30` and prints a report diff-identical to HLASM `SMFRPT30`'s, plus `--json`.

**Architecture:** Golden-first: capture the HLASM report as the golden file, stage the dataset with BDW/RDWs via the IEBGENER RECFM=U trick, pin the section/field offsets empirically with a discovery script (known values from artifact 5 make every offset findable), then TDD the parser against synthetic fixtures + the golden report.

**Tech Stack:** IBM Open Enterprise SDK for Python 3.13 (`/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3`), stdlib only (struct, json, unittest); JCL (IEBGENER, BPXBATCH); Zowe CLI from PowerShell with `--host zos31.pok.stglabs.ibm.com` (never Git Bash for USS work; hostname, not IP).

**Spec:** `docs/superpowers/specs/2026-07-09-python-smf-reader-design.md`

**Known facts (do not re-derive):**
- Records: 316 bytes incl. RDW (header 228 + ID section 72 @ offset 228 + CAS section 16 @ offset 300); 3 records for jobs `ANDREJ1`, `PAYROLL`, `BACKUP`.
- Golden report body (artifact 5 verified run):
  ```
  SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT
    JOB NAME        CPU (SEC)    ELAPSED (SEC)
    ANDREJ1            130.23          500.00
    PAYROLL           2515.00         3600.00
    BACKUP             100.00          120.00
  ```
- CPU = (SMF30CPT+SMF30CPS)/100 sec; ELAPSED = (SMF30TME−SMF30RST)/100 sec.
- Header offsets **verified by the 2026-07-09 smoke test** (incl. RDW): RDW@0(4), type@5 (=30), TME@6-9, DTE@10-13, SID@14-17, subtype@22-23. Triplet header offsets below are candidates only; Task 2's discovery output is authoritative.

---

### Task 1: Golden capture — run HLASM SMFRPT30 and save its report

**Files:**
- Create: `12-python-smf-reader/jcl/RUNRPT30.jcl`
- Create: `tmp/artifact12/golden-report.txt` (scratch; the committed copy goes into DESIGN.md later)

- [ ] **Step 1: Write the report-only JCL** (do NOT rerun MKSMF30 — it would scratch and rebuild the dataset; we want the exact bytes the smoke test validated)

`12-python-smf-reader/jcl/RUNRPT30.jcl`:
```jcl
//ANDRER30 JOB AMS-CLEAN,ANDRE,NOTIFY=ANDRE,CLASS=A,MSGLEVEL=(1,1)
//* Run artifact 5's SMFRPT30 alone against ANDRE.EPE.SMF30
//RPT      EXEC PGM=SMFRPT30
//STEPLIB  DD DSN=ANDRE.EPE.LOAD,DISP=SHR
//INDD     DD DSN=ANDRE.EPE.SMF30,DISP=SHR
//RPTDD    DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
```

- [ ] **Step 2: Submit and capture the golden report**

```powershell
$H='zos31.pok.stglabs.ibm.com'
zowe jobs submit local-file "c:\Users\075949631\Documents\Zowe\mainframe-portfolio\12-python-smf-reader\jcl\RUNRPT30.jcl" --wait-for-output --host $H
# then, with the returned JOBID:
zowe jobs view all-spool-content <JOBID> --host $H
```
Expected: RC 0000 and the golden body above. Save the RPTDD portion (exactly as spooled, minus JES banners) to `tmp\artifact12\golden-report.txt` (PowerShell `Set-Content -Encoding utf8`; keep column fidelity — do not re-wrap or trim line interiors).

- [ ] **Step 3: Commit the JCL**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 12-python-smf-reader/jcl/RUNRPT30.jcl
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 12: report-only JCL for golden capture of SMFRPT30 output"
```

---

### Task 2: Stage with BDW/RDW + empirical offset discovery

**Files:**
- Create: `12-python-smf-reader/jcl/STAGEVB.jcl`
- Create: `tmp/artifact12/discover.py` (scratch, not committed; findings go to DESIGN.md)
- Create: `12-python-smf-reader/docs/DESIGN.md` (layout findings section)

- [ ] **Step 1: Write the staging JCL** — read VB as RECFM=U so blocks arrive with BDW/RDWs

`12-python-smf-reader/jcl/STAGEVB.jcl`:
```jcl
//ANDRESTG JOB AMS-CLEAN,ANDRE,NOTIFY=ANDRE,CLASS=A,MSGLEVEL=(1,1)
//* Stage ANDRE.EPE.SMF30 to USS preserving BDW/RDWs (read VB as U)
//STAGE    EXEC PGM=IEBGENER
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSUT1   DD DSN=ANDRE.EPE.SMF30,DISP=SHR,
//            DCB=(RECFM=U,BLKSIZE=32760)
//SYSUT2   DD PATH='/z/andre/smf30.bin',
//            PATHOPTS=(OWRONLY,OCREAT,OTRUNC),
//            PATHMODE=(SIRUSR,SIWUSR,SIRGRP),
//            FILEDATA=BINARY
```

- [ ] **Step 2: Submit and verify the staged bytes start with a BDW**

```powershell
zowe jobs submit local-file "...\12-python-smf-reader\jcl\STAGEVB.jcl" --wait-for-output --host $H
zowe uss issue ssh 'od -An -tx1 -N 12 /z/andre/smf30.bin; ls -l /z/andre/smf30.bin'
```
Expected: first halfword = block length (e.g. 3×316+4=952=0x03B8), bytes 4-5 = `01 3c` (RDW length 316 = 0x013C). If the FIRST halfword is `01 3c`, IEBGENER delivered RDW-first records without BDW — fine; the discovery script and parser handle both modes.

- [ ] **Step 3: Write and run the discovery script** (pins every offset from known values)

`tmp/artifact12/discover.py` — upload `--binary`, `chtag -tc ISO8859-1 /z/andre/discover.py`, run with the host python3:
```python
import struct

D = open('/z/andre/smf30.bin', 'rb').read()
print('file bytes:', len(D))

# --- outer structure: BDW+RDW or RDW-only? ---
first = struct.unpack('>H', D[0:2])[0]
records = []
if first == 316:                      # RDW-first, no BDW
    mode = 'RDW-only'
    i = 0
    while i + 4 <= len(D):
        l = struct.unpack('>H', D[i:i+2])[0]
        records.append(D[i:i+l]); i += l
else:                                 # BDW(4) then RDWs inside the block
    mode = 'BDW+RDW'
    i = 0
    while i + 4 <= len(D):
        bl = struct.unpack('>H', D[i:i+2])[0]
        j, end = i + 4, i + bl
        while j + 4 <= end:
            rl = struct.unpack('>H', D[j:j+2])[0]
            records.append(D[j:j+rl]); j += rl
        i = end
print('mode:', mode, 'records:', len(records),
      'lengths:', [len(r) for r in records])

# --- header triplets: find (fullword offset, halfword len, halfword count) ---
r = records[0]
for off in range(24, 220, 2):
    f = struct.unpack('>I', r[off:off+4])[0]
    l, c = struct.unpack('>HH', r[off+4:off+8])
    if (f, l, c) in ((228, 72, 1), (300, 16, 1)):
        print('triplet at header offset', off, '->', (f, l, c))

# --- ID section: jobname + find SMF30RST by arithmetic ---
GOLD = {'ANDREJ1': 50000, 'PAYROLL': 360000, 'BACKUP': 12000}   # elapsed, 1/100 s
for r in records:
    ids = r[228:300]
    jbn = ids[0:8].decode('cp1047').rstrip()
    tme = struct.unpack('>I', r[6:10])[0]
    want = tme - GOLD[jbn]
    hits = [o for o in range(0, 68)
            if struct.unpack('>I', ids[o:o+4])[0] == want]
    print(jbn, 'TME', tme, 'RST candidates at ID+', hits)

# --- CAS section: CPT/CPS by arithmetic ---
GCPU = {'ANDREJ1': 13023, 'PAYROLL': 251500, 'BACKUP': 10000}   # cpu, 1/100 s
for r in records:
    jbn = r[228:236].decode('cp1047').rstrip()
    cas = r[300:316]
    words = [struct.unpack('>I', cas[o:o+4])[0] for o in (0, 4, 8, 12)]
    print(jbn, 'CAS words', words, 'need sum', GCPU[jbn])
```
Expected: mode identified; two triplet lines (the header offsets of `SMF30IOF` and `SMF30COF`); one consistent `RST` offset across all 3 jobs; two CAS words summing to the golden CPU for every job (their offsets = `SMF30CPT`, `SMF30CPS`). **These printed offsets are authoritative for Task 3's `*_AT` constants.**

- [ ] **Step 4: Record findings in `12-python-smf-reader/docs/DESIGN.md`** — create it with a `## Record layout (empirically pinned on ZOS31)` section: a table of field → offset → evidence (which known value pinned it), the BDW/RDW mode found, and the staging explanation (a `DCB=(RECFM=U)` override on SYSUT1 makes IEBGENER read raw blocks of the VB dataset, descriptor words intact).

- [ ] **Step 5: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 12-python-smf-reader/jcl/STAGEVB.jcl 12-python-smf-reader/docs/DESIGN.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 12: BDW/RDW staging JCL and empirically pinned record layout"
```

---

### Task 3: TDD the parser (tests + smfrpt30.py)

**Files:**
- Create: `12-python-smf-reader/src/smfrpt30.py`
- Create: `12-python-smf-reader/tests/test_smfrpt30.py`
- Host copies live under `/z/andre/a12/` mirroring `src/` and `tests/`.

- [ ] **Step 1: Write the failing test** — builds synthetic 316-byte records with the Task-2 offsets (imported from the implementation module so test and code cannot drift) and asserts parse/report/JSON/error behavior:

`12-python-smf-reader/tests/test_smfrpt30.py`:
```python
import json, os, struct, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import smfrpt30 as M


def mkrec(jbn, tme, rst, cpt, cps, rty=30, stp=5):
    r = bytearray(316)
    struct.pack_into('>H', r, 0, 316)                 # RDW
    r[5] = rty
    struct.pack_into('>I', r, 6, tme)
    struct.pack_into('>H', r, 22, stp)
    struct.pack_into('>IHH', r, M.IOF_AT, 228, 72, 1) # ID triplet
    struct.pack_into('>IHH', r, M.COF_AT, 300, 16, 1) # CAS triplet
    r[228:236] = jbn.ljust(8).encode('cp1047')
    struct.pack_into('>I', r, 228 + M.RST_AT, rst)
    struct.pack_into('>I', r, 300 + M.CPT_AT, cpt)
    struct.pack_into('>I', r, 300 + M.CPS_AT, cps)
    return bytes(r)


def blockof(*recs):
    body = b''.join(recs)
    return struct.pack('>HH', len(body) + 4, 0) + body


class TestParse(unittest.TestCase):
    def test_golden_row(self):
        rec = mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)
        rows = M.parse(blockof(rec))
        self.assertEqual(rows, [('PAYROLL', 251500, 360000)])

    def test_skips_other_types(self):
        rec = mkrec('NOPE', 100, 0, 1, 1, rty=70)
        self.assertEqual(M.parse(blockof(rec)), [])

    def test_report_matches_golden_format(self):
        rows = [('ANDREJ1', 13023, 50000),
                ('PAYROLL', 251500, 360000),
                ('BACKUP', 10000, 12000)]
        want = (
            'SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT\n'
            '  JOB NAME        CPU (SEC)    ELAPSED (SEC)\n'
            '  ANDREJ1            130.23          500.00\n'
            '  PAYROLL           2515.00         3600.00\n'
            '  BACKUP             100.00          120.00\n')
        self.assertEqual(M.report(rows), want)

    def test_json(self):
        rows = [('BACKUP', 10000, 12000)]
        got = json.loads(M.to_json(rows))
        self.assertEqual(got, [{'job': 'BACKUP',
                                'cpu_sec': 100.0, 'elapsed_sec': 120.0}])

    def test_truncated_record_raises(self):
        rec = mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)[:100]
        bad = struct.pack('>HH', 104, 0) + rec
        with self.assertRaises(M.ParseError):
            M.parse(bad)


if __name__ == '__main__':
    unittest.main()
```
NOTE: the `want` string in `test_report_matches_golden_format` is transcribed
from the golden capture — after Task 1, re-check it against
`tmp/artifact12/golden-report.txt` character-for-character (including the
two leading spaces per line) and correct if the spool differs.

- [ ] **Step 2: Run tests on the host, verify they FAIL** (module missing)

```powershell
zowe uss issue ssh 'mkdir -p /z/andre/a12/src /z/andre/a12/tests'
zowe zos-files upload file-to-uss "...\tests\test_smfrpt30.py" "/z/andre/a12/tests/test_smfrpt30.py" --binary --host $H
zowe uss issue ssh 'chtag -tc ISO8859-1 /z/andre/a12/tests/test_smfrpt30.py; /apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 /z/andre/a12/tests/test_smfrpt30.py'
```
Expected: `ModuleNotFoundError: No module named 'smfrpt30'`.

- [ ] **Step 3: Write the implementation**

`12-python-smf-reader/src/smfrpt30.py` — replace the five `*_AT` constants with Task-2 discovered values; everything else is complete:
```python
"""Python twin of HLASM SMFRPT30: reads BDW/RDW-staged SMF type-30
subtype-5 records and prints the identical CPU/elapsed report.
Stdlib only. Exit codes: 0 report, 4 no subtype-5 records, 8 bad input."""
import argparse, json, struct, sys

# Offsets pinned empirically on ZOS31 (see docs/DESIGN.md).  CANDIDATE
# values below; Task 2 discovery output is authoritative.
IOF_AT = 32      # header offset of SMF30IOF triplet
COF_AT = 40      # header offset of SMF30COF triplet
RST_AT = 24      # SMF30RST offset within ID section
CPT_AT = 0       # SMF30CPT offset within CAS section
CPS_AT = 4       # SMF30CPS offset within CAS section

RTY_AT, TME_AT, STP_AT = 5, 6, 22
HDR = 'SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT'
COLS = '  JOB NAME        CPU (SEC)    ELAPSED (SEC)'


class ParseError(Exception):
    pass


def _records(data):
    """Yield records (incl. RDW) from BDW+RDW blocks or a bare RDW stream."""
    if len(data) < 4:
        raise ParseError('input shorter than one descriptor word')
    first = struct.unpack('>H', data[0:2])[0]
    i = 0
    if first > 316:                       # plausible BDW (includes itself)
        while i + 4 <= len(data):
            bl = struct.unpack('>H', data[i:i+2])[0]
            if bl < 8 or i + bl > len(data):
                raise ParseError('bad BDW length %d at offset %d' % (bl, i))
            j, end = i + 4, i + bl
            while j + 4 <= end:
                rl = struct.unpack('>H', data[j:j+2])[0]
                if rl < 4 or j + rl > end:
                    raise ParseError('bad RDW length %d at offset %d'
                                     % (rl, j))
                yield data[j:j+rl]
                j += rl
            i = end
    else:                                 # RDW-only stream
        while i + 4 <= len(data):
            rl = struct.unpack('>H', data[i:i+2])[0]
            if rl < 4 or i + rl > len(data):
                raise ParseError('bad RDW length %d at offset %d' % (rl, i))
            yield data[i:i+rl]
            i += rl


def _triplet(rec, at):
    off = struct.unpack('>I', rec[at:at+4])[0]
    ln, cnt = struct.unpack('>HH', rec[at+4:at+8])
    return off, ln, cnt


def parse(data):
    """Return [(jobname, cpu_hundredths, elapsed_hundredths), ...]"""
    rows = []
    for rec in _records(data):
        if len(rec) < 24:
            raise ParseError('record shorter than SMF header (%d)' % len(rec))
        if rec[RTY_AT] != 30:
            continue
        if struct.unpack('>H', rec[STP_AT:STP_AT+2])[0] != 5:
            continue
        ioff, iln, ion = _triplet(rec, IOF_AT)
        coff, cln, con = _triplet(rec, COF_AT)
        if ion == 0 or con == 0:          # absent section: skip, like SMFRPT30
            continue
        if ioff + iln > len(rec) or coff + cln > len(rec):
            raise ParseError('triplet points past record end')
        ids, cas = rec[ioff:ioff+iln], rec[coff:coff+cln]
        jbn = ids[0:8].decode('cp1047').rstrip()
        tme = struct.unpack('>I', rec[TME_AT:TME_AT+4])[0]
        rst = struct.unpack('>I', ids[RST_AT:RST_AT+4])[0]
        cpt = struct.unpack('>I', cas[CPT_AT:CPT_AT+4])[0]
        cps = struct.unpack('>I', cas[CPS_AT:CPS_AT+4])[0]
        rows.append((jbn, cpt + cps, tme - rst))
    return rows


def report(rows):
    out = [HDR, COLS]
    for jbn, cpu, ela in rows:
        out.append('  %-8s %12.2f %15.2f' % (jbn, cpu / 100, ela / 100))
    return '\n'.join(out) + '\n'


def to_json(rows):
    return json.dumps([{'job': j, 'cpu_sec': c / 100, 'elapsed_sec': e / 100}
                       for j, c, e in rows])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stagefile', help='USS binary staging file (BDW/RDW)')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args(argv)
    try:
        data = open(a.stagefile, 'rb').read()
        if not data:
            raise ParseError('staging file is empty')
        rows = parse(data)
    except (OSError, ParseError) as e:
        print('SMFRPT30PY ERROR:', e, file=sys.stderr)
        return 8
    if not rows:
        print('SMFRPT30PY: no type 30 subtype 5 records', file=sys.stderr)
        return 4
    sys.stdout.write(to_json(rows) + '\n' if a.as_json else report(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
```
NOTE: the detail-line format `'  %-8s %12.2f %15.2f'` is a candidate — Task
4's empty diff against the golden file is the authority; adjust widths there
if needed and re-run the unit tests (the `want` string and format must move
together).

- [ ] **Step 4: Upload implementation, run tests, verify PASS**

```powershell
zowe zos-files upload file-to-uss "...\src\smfrpt30.py" "/z/andre/a12/src/smfrpt30.py" --binary --host $H
zowe uss issue ssh 'chtag -tc ISO8859-1 /z/andre/a12/src/smfrpt30.py; /apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 /z/andre/a12/tests/test_smfrpt30.py'
```
Expected: `Ran 5 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 12-python-smf-reader/src/smfrpt30.py 12-python-smf-reader/tests/test_smfrpt30.py
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 12: TDD parser passing unit tests on ZOS31 python"
```

---

### Task 4: Equivalence run — RUNPYRPT.jcl + diff against golden

**Files:**
- Create: `12-python-smf-reader/jcl/RUNPYRPT.jcl`
- Modify: `12-python-smf-reader/docs/DESIGN.md` (evidence + error archaeology)

- [ ] **Step 1: Write the end-to-end JCL** (stage + run; report to spool)

`12-python-smf-reader/jcl/RUNPYRPT.jcl`:
```jcl
//ANDREPY  JOB AMS-CLEAN,ANDRE,NOTIFY=ANDRE,CLASS=A,MSGLEVEL=(1,1)
//* Stage ANDRE.EPE.SMF30 (BDW/RDW intact) then report with python3
//STAGE    EXEC PGM=IEBGENER
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSUT1   DD DSN=ANDRE.EPE.SMF30,DISP=SHR,
//            DCB=(RECFM=U,BLKSIZE=32760)
//SYSUT2   DD PATH='/z/andre/smf30.bin',
//            PATHOPTS=(OWRONLY,OCREAT,OTRUNC),
//            PATHMODE=(SIRUSR,SIWUSR,SIRGRP),
//            FILEDATA=BINARY
//PYRPT    EXEC PGM=BPXBATCH,COND=(0,NE)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDPARM  DD *
SH /apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3
   /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin
/*
```

- [ ] **Step 2: Submit, pull both spools, diff**

```powershell
zowe jobs submit local-file "...\jcl\RUNPYRPT.jcl" --wait-for-output --host $H
zowe jobs view all-spool-content <JOBID> --host $H
# save the STDOUT report body to tmp\artifact12\python-report.txt, then:
git diff --no-index tmp\artifact12\golden-report.txt tmp\artifact12\python-report.txt
```
Expected: empty diff. The HLASM RPTDD is RECFM=FBA — if the spool shows the
ASA carriage-control column, strip column 1 from the golden capture and note
that in DESIGN.md. If column widths differ: adjust `report()`'s format string
AND the test's `want` string, re-upload, resubmit — loop until the diff is
empty. Record every iteration in `## Error archaeology`.

- [ ] **Step 3: JSON check**

```powershell
zowe uss issue ssh '/apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3 /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin --json'
```
Expected: one-line JSON array; `cpu_sec` values 130.23 / 2515.0 / 100.0.

- [ ] **Step 4: Write the evidence** in `docs/DESIGN.md`: `## Evidence of the verified run (ZOS31, <date>)` — JOBIDs + RCs of RUNRPT30 and RUNPYRPT (both steps), the empty-diff proof, the JSON line; plus `## Error archaeology` rows for every real error hit in Tasks 1–4.

- [ ] **Step 5: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 12-python-smf-reader/jcl/RUNPYRPT.jcl 12-python-smf-reader/docs/DESIGN.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 12: verified HLASM/Python report equivalence on ZOS31"
```

---

### Task 5: Documentation and repo integration

**Files:**
- Create: `12-python-smf-reader/README.md`
- Modify: `README.md` (row 12 after row 11; layout line after `11-rest-workflow/`)
- Modify: `CLAUDE.md` (scope 11 → 12; item 12 after item 11; status row 12)

- [ ] **Step 1: Write `12-python-smf-reader/README.md`** following the exact structure of `11-rest-workflow/README.md`: title `# Artifact 12 — Python SMF Type-30 Reader (IBM Open Enterprise SDK for Python)`; summary paragraph (Python re-reads what artifact 5's HLASM wrote; diff-identical report); "Verified on ..." with the real JOBIDs/RCs from Task 4; `## What it demonstrates` (IBM Python 3.13 on z/OS; BDW/RDW block parsing = real SMF dump handling; the RECFM=U staging trick; EBCDIC cp1047 + big-endian struct decode; triplet navigation mirroring the DSECT walk; diffable HLASM↔Python equivalence + `--json`); `## Layout`; `## Running it (Zowe CLI)` with the exact submit/view commands and the `--host` hostname note; `## Interview talking points` (3 bullets drawn from the error archaeology).

- [ ] **Step 2: Top-level README** — append after row 11:
```markdown
| 12 | [Python SMF Reader](12-python-smf-reader/) | Modern languages on z/OS — IBM Open Enterprise SDK for Python re-reads the SMF type-30 dataset artifact 5's HLASM wrote (BDW/RDW block parsing, EBCDIC + big-endian struct decode, triplet navigation) and prints a report diff-identical to SMFRPT30's, plus JSON. |
```
and in the layout block after the `11-rest-workflow/` line:
```
  12-python-smf-reader/  src/ tests/ jcl/ docs/ README.md
```

- [ ] **Step 3: CLAUDE.md** — `## Portfolio scope — 11 artifacts` → `## Portfolio scope — 12 artifacts`; append after item 11:
```markdown
12. **Python SMF Reader** (`12-python-smf-reader/`)
    IBM Open Enterprise SDK for Python (3.13) re-reads artifact 5's
    ANDRE.EPE.SMF30: JCL stages the VB dataset as RECFM=U (BDW/RDWs
    intact), pure-stdlib Python walks blocks/records/triplets and prints
    a report diff-identical to SMFRPT30's, plus --json. Verified on ZOS31.
```
and append to the status table: `| 12 | Python SMF Reader     | Complete    |`

- [ ] **Step 4: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 12-python-smf-reader/README.md README.md CLAUDE.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Add artifact 12: Python SMF type-30 reader"
```

---

### Task 6: Final verification and push

- [ ] **Step 1: Working tree + history**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio status -sb
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio log --oneline shop/master..master
```
Expected: clean tree (untracked `tmp/` ok); commits = spec + plan + the artifact-12 commits.

- [ ] **Step 2: Spec success criteria** — all four: runs under host Python 3.13 with RC 0; report diff-identical; valid `--json`; repo conventions followed. Stop and resolve before pushing if any fail.

- [ ] **Step 3: Host cleanup** (definition of done: no scratch files on the host; the JCL re-creates staging at will)

```powershell
zowe uss issue ssh 'rm -rf /z/andre/a12 /z/andre/smf30.bin /z/andre/discover.py'
```

- [ ] **Step 4: Push — confirm with the user first (repo custom)**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio push shop master
```

---

## Self-review notes

- **Spec coverage:** golden capture + equivalence diff (Tasks 1, 4), RECFM=U staging (Tasks 2, 4), empirical offsets (Task 2), stdlib parser + RC 0/4/8 + `--json` (Task 3), docs/integration (Task 5), push (Task 6). Non-goals respected (no pip/ZOAU/venv; synthetic data only).
- **Known candidates, by design:** the five `*_AT` offsets (Task 2 discovery authoritative) and the `report()` format string + test `want` string (Task 4's empty diff authoritative) — marked at their definition sites; test imports the constants from the module so they cannot drift.
- **Consistency:** golden numbers everywhere trace to artifact 5's verified report (`13023/50000`, `251500/360000`, `10000/12000` hundredths); host paths consistently `/z/andre/a12/...` and `/z/andre/smf30.bin`; every zowe call uses `--host zos31.pok.stglabs.ibm.com`.
