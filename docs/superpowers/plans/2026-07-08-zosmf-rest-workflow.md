# Artifact 11: z/OSMF Self-Inventory Workflow (rest + setVariable) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, verify on ZOS31, and publish portfolio artifact 11 — a z/OSMF workflow that exercises the `rest` and `setVariable` step action types, proving a value captured/set in an early step flows into a final shell-JCL report step.

**Architecture:** Discovery-first: extract the real `rest`/`setVariable` syntax from `workflow_v1.xsd` and IBM's samples on the host, then author one workflow XML (4 steps: rest → setVariable → rest → shell-JCL), validate it through the register/`--steps-summary-only` loop, run it, and package it as `11-rest-workflow/` following the repo's artifact conventions.

**Tech Stack:** z/OSMF workflow engine (z/OS 3.1, system nickname `ZOS31`), Zowe CLI from PowerShell (never Git Bash for USS paths), git.

**Spec:** `docs/superpowers/specs/2026-07-08-zosmf-rest-workflow-design.md`

**Ground rules (from hard-won memory — violating these costs hours):**
- Workflow XML uploads with `--binary`; verify first bytes are `3C 3F 78 6D 6C`.
- `${instance-NAME}` prefix for instance variables; bare `${NAME}` passes through literally.
- With `substitution="true"`, shell forms `${VAR:-x}`, `${#VAR}`, `${VAR/a/b}` crash the parser (IZUWF0084E) — plain `$shellvar` and `$(...)` only.
- `successPattern` forbidden on shell-JCL steps (IZUWF0303E).
- Don't `--overwrite` an in-progress instance — create a new one instead.
- Run all `zowe` commands with USS paths from PowerShell.

---

### Task 1: Discovery — extract real `rest`/`setVariable` syntax from XSD and samples

**Files:**
- Create: `tmp/discovery/` (scratch, not committed)
- Create: `11-rest-workflow/docs/DESIGN.md` (findings section only; grows in later tasks)

- [ ] **Step 1: Locate and download the workflow XSD**

Run (PowerShell):
```powershell
zowe zos-files list uss-files "/Z31RS1/usr/lpp/zosmf/workflow/schemas"
```
Expected: a listing containing `workflow_v1.xsd` (name may carry a version suffix; use what's listed). Then:
```powershell
New-Item -ItemType Directory -Force tmp\discovery | Out-Null
zowe zos-files download uss-file "/Z31RS1/usr/lpp/zosmf/workflow/schemas/workflow_v1.xsd" --file tmp\discovery\workflow_v1.xsd --binary
```
If the schemas directory is not at that path, find it: `zowe zos-files list uss-files "/Z31RS1/usr/lpp/zosmf"` and descend into the likely `workflow/` subdirectory.

- [ ] **Step 2: Extract the `rest` and `setVariable` type definitions from the XSD**

Run (Grep tool or PowerShell Select-String on the local file):
```powershell
Select-String -Path tmp\discovery\workflow_v1.xsd -Pattern 'rest|setVariable|propertyMapping|httpMethod|uriPath|statusCode|expression' -Context 3
```
Record: the exact child-element names, order, and which are required. These findings are authoritative and override the candidate XML in Task 2.

- [ ] **Step 3: Download IBM sample workflows and grep for real usage**

Run:
```powershell
zowe zos-files list uss-files "/Z31RS1/usr/lpp/zosmf/samples"
# download every *.xml sample (they are ASCII-tagged; --binary keeps the bytes readable locally)
zowe zos-files download uss-file "/Z31RS1/usr/lpp/zosmf/samples/<name>.xml" --file tmp\discovery\<name>.xml --binary
```
Then locally:
```powershell
Select-String -Path tmp\discovery\*.xml -Pattern '<rest>|<setVariable|propertyMapping|httpMethod' -Context 5
```
Expected: at least one sample using `rest` and/or `setVariable`. If none uses them, the XSD alone is ground truth — note that.

- [ ] **Step 4: Write the findings into `11-rest-workflow/docs/DESIGN.md`**

Create the file with a `## Schema findings (from workflow_v1.xsd + samples)` section quoting the actual XSD fragments for `rest` and `setVariable` (element names, required children, how response values map to variables — or the finding that they cannot).

- [ ] **Step 5: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 11-rest-workflow/docs/DESIGN.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 11: schema findings for rest/setVariable step types"
```

---

### Task 2: Author the workflow XML and validate it via the register loop

**Files:**
- Create: `11-rest-workflow/workflow/rest-inventory.xml`

- [ ] **Step 1: Write the workflow XML**

Start from this candidate and **correct every `rest`/`setVariable` construct against Task 1's findings before first upload** (the two `template` steps and the workflow skeleton below use proven syntax and should not need changes):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<workflow xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:noNamespaceSchemaLocation="workflow_v1.xsd">

    <workflowInfo>
        <workflowID>rest-inventory</workflowID>
        <workflowDefaultName>REST Inventory</workflowDefaultName>
        <workflowDescription>Self-inventory of the z/OSMF instance using rest and setVariable steps</workflowDescription>
        <workflowVersion>1.0</workflowVersion>
        <vendor>Custom</vendor>
    </workflowInfo>

    <variable name="INFO_VERSION" scope="instance" visibility="public">
        <label>z/OSMF Version</label>
        <abstract>Captured from GET /zosmf/info</abstract>
        <description>Filled by the getInfo rest step</description>
        <category>Inventory</category>
        <string/>
    </variable>

    <variable name="REPORT_NAME" scope="instance" visibility="public">
        <label>Report Name</label>
        <abstract>Derived by the setVariable step</abstract>
        <description>Filled by the deriveNames setVariable step</description>
        <category>Inventory</category>
        <string/>
    </variable>

    <variable name="PROBE_JOBID" scope="instance" visibility="public">
        <label>Probe JOBID</label>
        <abstract>JOBID returned by the job-submit rest step</abstract>
        <description>Filled by the submitProbe rest step</description>
        <category>Inventory</category>
        <string/>
    </variable>

    <step name="getInfo" optional="false">
        <title>Query z/OSMF Info</title>
        <description>Calls GET /zosmf/info and captures the version</description>
        <instructions substitution="true">
            <p>Queries the z/OSMF info endpoint and captures the version into INFO_VERSION.</p>
        </instructions>
        <weight>1</weight>
        <autoEnable>true</autoEnable>
        <canMarkAsFailed>true</canMarkAsFailed>
        <!-- CANDIDATE SYNTAX: correct against Task 1 XSD findings -->
        <rest>
            <httpMethod>GET</httpMethod>
            <uriPath substitution="true">/zosmf/info</uriPath>
            <expectedStatusCode>200</expectedStatusCode>
            <propertyMappings>
                <propertyMapping mapFrom="api_version" mapTo="INFO_VERSION"/>
            </propertyMappings>
        </rest>
    </step>

    <step name="deriveNames" optional="false">
        <title>Derive Report Name</title>
        <description>Sets REPORT_NAME from the captured version</description>
        <instructions substitution="true">
            <p>Builds the report name from INFO_VERSION.</p>
        </instructions>
        <weight>1</weight>
        <autoEnable>true</autoEnable>
        <canMarkAsFailed>true</canMarkAsFailed>
        <prereqStep name="getInfo"/>
        <!-- CANDIDATE SYNTAX: correct against Task 1 XSD findings -->
        <setVariable name="REPORT_NAME">
            <expression>inventory-${instance-INFO_VERSION}</expression>
        </setVariable>
    </step>

    <step name="submitProbe" optional="false">
        <title>Submit Probe Job</title>
        <description>Submits a trivial IEFBR14 job via the jobs REST API and captures its JOBID</description>
        <instructions substitution="true">
            <p>Submits an IEFBR14 probe job through PUT /zosmf/restjobs/jobs and captures the returned jobid into PROBE_JOBID.</p>
        </instructions>
        <weight>2</weight>
        <autoEnable>true</autoEnable>
        <canMarkAsFailed>true</canMarkAsFailed>
        <prereqStep name="deriveNames"/>
        <!-- CANDIDATE SYNTAX: correct against Task 1 XSD findings.
             FALLBACK if requestBody/headers are unsupported for job submit:
             change to GET /zosmf/restjobs/jobs?owner=ANDRE&amp;prefix=* judged by
             status code only, and drop the PROBE_JOBID capture (document the
             limitation in DESIGN.md). -->
        <rest>
            <httpMethod>PUT</httpMethod>
            <uriPath substitution="true">/zosmf/restjobs/jobs</uriPath>
            <requestBody substitution="true">//ANDREP   JOB AMS-CLEAN,ANDRE,NOTIFY=ANDRE,CLASS=A,MSGLEVEL=(1,1)
//STEP1    EXEC PGM=IEFBR14</requestBody>
            <expectedStatusCode>201</expectedStatusCode>
            <propertyMappings>
                <propertyMapping mapFrom="jobid" mapTo="PROBE_JOBID"/>
            </propertyMappings>
        </rest>
    </step>

    <step name="writeReport" optional="false">
        <title>Write Inventory Report</title>
        <description>Echoes every captured/derived value, proving cross-step variable flow</description>
        <instructions substitution="true">
            <p>Prints the inventory built from values produced by the earlier steps.</p>
        </instructions>
        <weight>1</weight>
        <autoEnable>true</autoEnable>
        <canMarkAsFailed>true</canMarkAsFailed>
        <prereqStep name="submitProbe"/>
        <template>
            <inlineTemplate substitution="true">
#!/bin/sh
echo "===== z/OSMF SELF-INVENTORY ====="
echo "z/OSMF version : ${instance-INFO_VERSION}"
echo "Report name    : ${instance-REPORT_NAME}"
echo "Probe JOBID    : ${instance-PROBE_JOBID}"
echo "================================="
if [ -z "${instance-INFO_VERSION}" ]; then
  echo "ERROR: INFO_VERSION did not flow from the rest step"
  exit 1
fi
echo "SUCCESS: variables flowed across step types"
            </inlineTemplate>
            <submitAs>shell-JCL</submitAs>
            <maxLrecl>1024</maxLrecl>
        </template>
    </step>

</workflow>
```

- [ ] **Step 2: Upload to the host**

```powershell
zowe zos-files upload file-to-uss "c:\Users\075949631\Documents\Zowe\mainframe-portfolio\11-rest-workflow\workflow\rest-inventory.xml" "/z/andre/rest-inventory.xml" --binary
```

- [ ] **Step 3: Register — this is the failing-test loop**

```powershell
zowe zos-workflows create workflow-from-uss-file "REST Inventory" --uss-file /z/andre/rest-inventory.xml --system-name ZOS31 --owner andre --assign-to-owner --overwrite
```
Expected initially: **validation errors with line numbers** (the candidate `rest`/`setVariable` syntax will likely be wrong somewhere). Loop: fix local XML → re-upload (Step 2) → re-create, until create succeeds. Record every distinct error code + fix in `11-rest-workflow/docs/DESIGN.md` under `## Error archaeology`. `--overwrite` is safe here because no step has been started yet.

- [ ] **Step 4: Run the fast validation gate**

```powershell
zowe zos-workflows list active-workflow-details --workflow-key <key-from-create-output> --steps-summary-only
```
Expected: 4 steps listed, no substitution errors (IZUWF0084E would surface here). All steps `Ready` or the first `Ready` and the rest `Not Ready`.

- [ ] **Step 5: Commit the validated definition**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 11-rest-workflow/workflow/rest-inventory.xml 11-rest-workflow/docs/DESIGN.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 11: rest-inventory workflow validates on ZOS31"
```

---

### Task 3: Execute the workflow and capture evidence

**Files:**
- Modify: `11-rest-workflow/docs/DESIGN.md` (evidence section)

- [ ] **Step 1: Run the steps in order**

```powershell
zowe zos-workflows start workflow-step getInfo --workflow-key <key>
zowe zos-workflows list active-workflow-details --workflow-key <key> --steps-summary-only
```
Wait for `getInfo` = `Complete` before starting the next; repeat for `deriveNames`, `submitProbe`, `writeReport`. rest and setVariable steps should complete near-instantly; shell-JCL completes quickly with a JOBID in the misc column.

- [ ] **Step 2: Verify the variables actually captured**

```powershell
zowe zos-workflows list active-workflow-details --workflow-key <key> --list-variables
```
Expected: `INFO_VERSION`, `REPORT_NAME`, `PROBE_JOBID` all non-null. If a capture is null, apply the spec's graceful degradation (status-code-only rest step) and document the limitation — that is an acceptable outcome per the spec.

- [ ] **Step 3: Pull the report step's spool as evidence**

```powershell
zowe jobs view all-spool-content <writeReport-JOBID> | Select-String -Pattern 'INVENTORY|version|JOBID|SUCCESS|ERROR'
```
Expected: the echoed inventory with real values and `SUCCESS: variables flowed across step types`.

- [ ] **Step 4: Record evidence in DESIGN.md**

Add `## Evidence of the verified run (ZOS31, <date>)` with the steps-summary table and the spool excerpt, same format as artifact 10's DESIGN.md.

- [ ] **Step 5: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 11-rest-workflow/docs/DESIGN.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Artifact 11: verified run evidence from ZOS31"
```

---

### Task 4: Documentation and repo integration

**Files:**
- Create: `11-rest-workflow/README.md`
- Modify: `README.md` ("What's inside" table after row 10; repository layout block)
- Modify: `CLAUDE.md` (scope list after item 10; status table; heading count 10 → 11)

- [ ] **Step 1: Write `11-rest-workflow/README.md`**

Follow the exact structure of `10-liberty-dump-workflow/README.md`: title (`# Artifact 11 — z/OSMF Self-Inventory Workflow (rest + setVariable)`), one-paragraph summary, a "Verified on ..." paragraph quoting the real step states/JOBIDs from Task 3, `## What it demonstrates` (completes the action-type trilogy; rest steps judged by expected status code; setVariable; cross-step variable flow; whatever auth finding Task 2/3 produced), `## Layout`, `## Running it (Zowe CLI)` with the exact commands used (upload `--binary`, create, `--steps-summary-only`, start steps, view spool), `## Interview talking points` (3 bullets drawn from the error archaeology).

- [ ] **Step 2: Add row 11 to the top-level README table**

Append after the row-10 line in `README.md`:
```markdown
| 11 | [z/OSMF REST Workflow](11-rest-workflow/) | Completing the workflow action-type trilogy — rest steps that call z/OSMF's own APIs (info, job submit) with response values captured into variables, a setVariable step, and a final shell step proving the values flow across step types. |
```
And in the repository layout block, after the `10-liberty-dump-workflow/` line:
```
  11-rest-workflow/      workflow/ docs/ README.md
```

- [ ] **Step 3: Update CLAUDE.md**

Change `## Portfolio scope — 10 artifacts` to `## Portfolio scope — 11 artifacts`. Append after item 10:
```markdown
11. **z/OSMF REST Workflow** (`11-rest-workflow/`)
    A z/OSMF workflow exercising the two remaining step action types:
    rest steps calling z/OSMF's own APIs with captured response values,
    and a setVariable step, feeding a final shell-JCL report that proves
    cross-step variable flow. Verified on ZOS31.
```
Append to the status table:
```markdown
| 11 | z/OSMF REST Workflow | Complete |
```

- [ ] **Step 4: Commit**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio add 11-rest-workflow/README.md README.md CLAUDE.md
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio commit -m "Add artifact 11: z/OSMF rest+setVariable self-inventory workflow"
```

---

### Task 5: Final verification and push

- [ ] **Step 1: Verify the working tree and history**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio status -sb
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio log --oneline shop/master..master
```
Expected: clean tree; the commits ahead are the two spec/plan commits plus the artifact-11 commits.

- [ ] **Step 2: Re-check success criteria against the spec**

All four spec criteria: registers cleanly; all steps Complete with ≥1 rest and 1 setVariable executed; ≥1 value visibly flowed into the report output; repo conventions followed. If any failed, stop and resolve before pushing.

- [ ] **Step 3: Push to Mainframe_Shop**

```powershell
git -C c:\Users\075949631\Documents\Zowe\mainframe-portfolio push shop master
```
Expected: `master -> master` fast-forward. Note: this also publishes the spec/plan docs under `docs/superpowers/`; confirm with the user at push time if they haven't already said to keep specs out of the public repo.

---

## Self-review notes

- **Spec coverage:** discovery-first (Task 1), 4-step workflow (Task 2), host files in `/z/andre` (Task 2 Step 2), verification loop + auth finding (Tasks 2–3), graceful degradation (Task 2 fallback comment + Task 3 Step 2), repo layout/README/CLAUDE.md (Task 4), push (Task 5). No spec section is untasked.
- **Known unknown, by design:** the `rest`/`setVariable` element syntax in Task 2's XML is explicitly a candidate; Task 1's XSD findings are declared authoritative and the register loop is the corrective test. This is the spec's discovery-first contract, not a placeholder.
- **Consistency:** variable names (`INFO_VERSION`, `REPORT_NAME`, `PROBE_JOBID`), step names (`getInfo`, `deriveNames`, `submitProbe`, `writeReport`), and file paths are identical across all tasks.
