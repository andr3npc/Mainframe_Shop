#!/usr/bin/env bash
# collect_and_report.sh — Zowe CLI glue for the z/OS Health Check Workflow
# =========================================================================
# Pulls the JES spool output from all five workflow steps, concatenates it
# into a single text file, then calls generate_report.py to produce the
# HTML scorecard.
#
# Prerequisites
# -------------
#   - Zowe CLI installed and a default profile configured
#   - Python 3.7+ on PATH
#   - The z/OS Health Check workflow has been registered and all steps
#     have completed successfully
#
# Usage
# -----
#   ./scripts/collect_and_report.sh <workflow-key>
#
# Example
#   ./scripts/collect_and_report.sh abc123def456
#
# The workflow key is printed by:
#   zowe zos-workflows create workflow-from-uss-file ...
# or listed by:
#   zowe zos-workflows list active-workflows

set -euo pipefail

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <workflow-key> [--keep-spool]" >&2
  echo "" >&2
  echo "  workflow-key  The z/OSMF workflow instance key" >&2
  echo "  --keep-spool  Keep the raw spool text file after the HTML is generated" >&2
  exit 1
fi

WORKFLOW_KEY="$1"
KEEP_SPOOL=false
if [[ "${2:-}" == "--keep-spool" ]]; then
  KEEP_SPOOL=true
fi

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="$(dirname "$SCRIPT_DIR")"
DATE_STAMP="$(date '+%Y%m%d_%H%M%S')"
SPOOL_FILE="${ARTIFACT_DIR}/tmp/spool_${DATE_STAMP}.txt"
REPORT_FILE="${ARTIFACT_DIR}/zos_health_report_${DATE_STAMP}.html"
GENERATE_PY="${SCRIPT_DIR}/generate_report.py"

mkdir -p "${ARTIFACT_DIR}/tmp"

echo "================================================================"
echo "z/OS Health Check — Collect and Report"
echo "Workflow key : ${WORKFLOW_KEY}"
echo "Spool file   : ${SPOOL_FILE}"
echo "Report file  : ${REPORT_FILE}"
echo "================================================================"

# ---------------------------------------------------------------------------
# Step names in the workflow (must match the XML step name= attributes)
# ---------------------------------------------------------------------------
STEPS=(
  spoolPressure
  cpuShapeAnalysis
  memoryPaging
  datasetHotspots
  healthScorecard
)

# ---------------------------------------------------------------------------
# Collect spool output from each step
# ---------------------------------------------------------------------------
echo "" > "${SPOOL_FILE}"   # create/truncate

for STEP in "${STEPS[@]}"; do
  echo "--- Collecting step: ${STEP} ---" >> "${SPOOL_FILE}"
  echo "" >> "${SPOOL_FILE}"

  # Get the list of jobs submitted by this step
  # zowe zos-workflows list step-info returns step details including the jobid
  STEP_JSON=$(zowe zos-workflows list active-workflow-details \
    --workflow-key "${WORKFLOW_KEY}" \
    --rfj 2>/dev/null || true)

  # Extract the jobid for this step from the workflow details JSON
  # Using python for portable JSON parsing — it's already a dependency
  JOBID=$(python3 - <<PYEOF
import json, sys
data = json.loads('''${STEP_JSON}''')
steps = data.get("data", {}).get("steps", [])
for s in steps:
    if s.get("name") == "${STEP}":
        jid = s.get("submitJobOutput", {}).get("jobid", "")
        if not jid:
            jid = s.get("jobInfo", {}).get("jobid", "")
        print(jid)
        sys.exit(0)
print("")
PYEOF
  )

  if [[ -z "${JOBID}" ]]; then
    echo "WARNING: No job ID found for step ${STEP} — step may not have run yet." >&2
    echo "[Step ${STEP}: no job output found]" >> "${SPOOL_FILE}"
    echo "" >> "${SPOOL_FILE}"
    continue
  fi

  echo "Step ${STEP}: job ${JOBID}"

  # Get the list of spool files for this job
  SPOOL_FILES_JSON=$(zowe jobs list spool-files-by-jobid "${JOBID}" --rfj 2>/dev/null || true)

  SPOOL_IDS=$(python3 - <<PYEOF
import json, sys
data = json.loads('''${SPOOL_FILES_JSON}''')
items = data.get("data", [])
# Prefer SYSTSPRT (TSO-REXX output) and stdout (shell-JCL output)
for item in items:
    ddname = item.get("ddname", "")
    if ddname in ("SYSTSPRT", "SYSPRINT", "STDOUT"):
        print(item.get("id", ""))
PYEOF
  )

  if [[ -z "${SPOOL_IDS}" ]]; then
    echo "WARNING: No SYSTSPRT/SYSPRINT/STDOUT spool files found for job ${JOBID}" >&2
    echo "[Step ${STEP} job ${JOBID}: no recognised spool DD found]" >> "${SPOOL_FILE}"
    echo "" >> "${SPOOL_FILE}"
    continue
  fi

  for SPOOL_ID in ${SPOOL_IDS}; do
    echo "  Fetching spool file ${SPOOL_ID}..."
    zowe jobs view spool-file-by-id "${JOBID}" "${SPOOL_ID}" \
      >> "${SPOOL_FILE}" 2>/dev/null || \
      echo "[Could not retrieve spool file ${SPOOL_ID} for job ${JOBID}]" >> "${SPOOL_FILE}"
  done

  echo "" >> "${SPOOL_FILE}"
done

echo "Spool collection complete. Lines: $(wc -l < "${SPOOL_FILE}")"
echo ""

# ---------------------------------------------------------------------------
# Validate that at least one VERDICT line was found
# ---------------------------------------------------------------------------
VERDICT_COUNT=$(grep -c "^VERDICT:" "${SPOOL_FILE}" || true)
if [[ "${VERDICT_COUNT}" -eq 0 ]]; then
  echo "ERROR: No VERDICT: lines found in collected spool output." >&2
  echo "       Verify all workflow steps completed successfully." >&2
  echo "       Raw spool saved to: ${SPOOL_FILE}" >&2
  exit 2
fi

echo "Found ${VERDICT_COUNT} VERDICT line(s) in spool output."

# ---------------------------------------------------------------------------
# Generate the HTML report
# ---------------------------------------------------------------------------
echo "Generating HTML report..."
python3 "${GENERATE_PY}" \
  --input  "${SPOOL_FILE}" \
  --output "${REPORT_FILE}"

echo ""
echo "================================================================"
echo "Report ready: ${REPORT_FILE}"
echo "================================================================"

# Open in default browser if on macOS or Linux desktop
if command -v open &>/dev/null; then
  open "${REPORT_FILE}"
elif command -v xdg-open &>/dev/null; then
  xdg-open "${REPORT_FILE}"
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
if [[ "${KEEP_SPOOL}" == false ]]; then
  rm -f "${SPOOL_FILE}"
fi

exit 0
