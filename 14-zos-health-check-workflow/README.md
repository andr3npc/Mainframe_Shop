# Artifact 14 — z/OS Health Check Workflow

A customer-facing z/OSMF **Workflow** that produces a full system health
snapshot across four cost axes in under 30 minutes. The workflow runs entirely
on the mainframe; a companion Python script pulls the results off JES spool and
renders a self-contained HTML scorecard with SVG gauges and a prioritised
action list.

## What it demonstrates

- **Customer-deliverable engineering** — not a lab exercise, but a tool a
  customer runs in a capacity review, hands to their management, and uses to
  justify hardware and software spend changes.
- **Multi-layer toolchain** — z/OSMF workflow (orchestration) + TSO-REXX
  (data collection) + Zowe CLI (extraction) + Python stdlib (report rendering)
  all in a single coherent pipeline.
- **Machine-readable REXX output** — every REXX step emits structured
  `VERDICT:` and `TOP_CONSUMER:` lines alongside the human-readable report,
  so the spool output is both operator-readable in the z/OSMF UI and
  machine-parseable by the Python script.
- **SMF record navigation** — the CPU and memory steps walk SMF-30 and SMF-70
  records using the same triplet-offset technique demonstrated in
  [Artifact 05](../05-smf30-reporter/), rewritten in REXX so no pre-compiled
  load module is needed at the customer site.
- **Zero pip dependencies** — `generate_report.py` uses only the Python
  standard library. It runs on any Python 3.7+ install without a
  `requirements.txt` or a virtual environment.

## The four axes

| Step | Axis | Data source | Cost lever |
|------|------|-------------|-----------|
| 1 | Spool pressure | SDSF SP + ST panels | JES DASD capacity |
| 2 | CPU shape | SMF type-30, subtype-5 | MLC software charges |
| 3 | Memory/paging | SMF type-70 (RMF) | Real storage sizing |
| 4 | Dataset I/O hotspots | SMF type-14/15 | Storage tier ROI |
| 5 | Scorecard sign-off | shell-JCL summary | Operator record |

## Layout

```
14-zos-health-check-workflow/
  workflow/
    zos_health_check.xml     ← workflow definition (5 steps, 9 variables)
  scripts/
    generate_report.py       ← parses VERDICT: lines, renders SVG HTML
    collect_and_report.sh    ← Zowe CLI glue: pulls spool, calls Python
  tmp/                       ← gitignored; spool text files land here
```

## VERDICT line format

Every REXX step emits one or more structured lines that `generate_report.py`
parses with a single regex:

```
VERDICT:<axis>:<value>:<threshold>:<grade>
TOP_CONSUMER:<axis>:<name>:<metric>
```

Example output from step 1:

```
VERDICT:SPOOL:73.40:80:AMBER
TOP_CONSUMER:SPOOL:PAYROLL:ANDRE:22.1%
TOP_CONSUMER:SPOOL:BACKUP01:SYS:18.4%
```

This design means the workflow output is useful in three ways:
1. Readable by an operator directly in the z/OSMF step log
2. Parseable by `generate_report.py` for the HTML scorecard
3. Greppable from a REXX or JCL follow-on step for alerting

## Running it

### 1. Upload the workflow XML

```bash
zowe zos-files upload file-to-uss workflow/zos_health_check.xml \
  /z/andre/zos_health_check.xml --binary
```

### 2. Register the workflow with site-specific thresholds

```bash
zowe zos-workflows create workflow-from-uss-file "z/OS Health Check" \
  --uss-file /z/andre/zos_health_check.xml \
  --system-name ZOS31 \
  --owner andre \
  --assign-to-owner \
  --variables "SMF_INPUT_DSN=PROD.SMF.MANX,MEASUREMENT_HOURS=48,SPOOL_HIGH_WATER=75"
```

Save the workflow key printed by this command.

### 3. Run the steps in sequence

```bash
WFKEY=<key from step above>

zowe zos-workflows start workflow-step spoolPressure    --workflow-key $WFKEY
zowe zos-workflows start workflow-step cpuShapeAnalysis --workflow-key $WFKEY
zowe zos-workflows start workflow-step memoryPaging     --workflow-key $WFKEY
zowe zos-workflows start workflow-step datasetHotspots  --workflow-key $WFKEY
zowe zos-workflows start workflow-step healthScorecard  --workflow-key $WFKEY
```

Or run all steps from the z/OSMF browser UI — the `prereqStep` chain enforces
the correct order automatically.

### 4. Generate the HTML scorecard

```bash
chmod +x scripts/collect_and_report.sh
./scripts/collect_and_report.sh $WFKEY
```

This pulls all step outputs off JES spool, merges them into
`tmp/spool_<timestamp>.txt`, calls `generate_report.py`, and opens
`zos_health_report_<date>.html` in your default browser.

To keep the raw spool file for auditing:

```bash
./scripts/collect_and_report.sh $WFKEY --keep-spool
```

To generate the report from an existing spool file:

```bash
python scripts/generate_report.py --input tmp/spool_20250716_142200.txt
```

## Scorecard output

The HTML file is fully self-contained (no external assets, no JavaScript).
It includes:

- An overall GREEN / AMBER / RED grade with a count of findings per level
- One SVG bar gauge per axis showing measured value vs. threshold, coloured
  by grade
- Top 5 consumers per axis (job names, owners, spool %, opens/hr)
- A prioritised action list ordered by grade (RED actions first), each action
  drawn from a curated library of mainframe housekeeping recommendations

The customer can email this file, open it in any browser, or screenshot it
directly into a capacity review slide.

## Workflow variables

| Variable | Default | Controls |
|----------|---------|----------|
| `SPOOL_HIGH_WATER` | `80` | Spool % at or above which the axis is RED |
| `TOP_N` | `10` | Top consumers listed in spool and dataset steps |
| `CPU_RATIO_RED` | `2` | CPU/elapsed % below which an STC is RED |
| `CPU_RATIO_AMBER` | `10` | CPU/elapsed % below which an STC is AMBER |
| `MIN_ELAPSED_HOURS` | `4` | STC must have run this long before CPU ratio is graded |
| `PGRATE_RED` | `100` | Page-ins/sec above which memory is RED |
| `PGRATE_AMBER` | `25` | Page-ins/sec above which memory is AMBER |
| `SMF_INPUT_DSN` | `SYS1.MAN1` | SMF archive dataset for steps 2–4 |
| `MEASUREMENT_HOURS` | `24` | Hours of SMF history to analyse |

## Portfolio connections

| Artifact | Technique reused |
|----------|-----------------|
| [13 — Spool Housekeeping](../13-spool-housekeeping-workflow/) | SDSF SP/ST REXX, ISFCALLS guard, TGNUM stem handling |
| [05 — SMF-30 Reporter](../05-smf30-reporter/) | IFASMFR(30) triplet navigation, CPU/elapsed field layout |
| [10 — Liberty Dump](../10-liberty-dump-workflow/) | `prereqStep` chaining, `successPattern` matching |
| [12 — Python SMF Reader](../12-python-smf-reader/) | Python + mainframe data, report generation pattern |
