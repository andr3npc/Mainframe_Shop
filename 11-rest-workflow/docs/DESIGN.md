# Artifact 11 — z/OSMF Self-Inventory Workflow (rest + setVariable): Design & Findings

## Schema findings (from workflow_v1.xsd + samples)

Source: `/Z31RS1/usr/lpp/zosmf/workflow/schemas/workflow_v1.xsd` (81,255 bytes, downloaded
2026-07-09). None of the 8 shipped IBM samples in `/Z31RS1/usr/lpp/zosmf/samples`
(`workflow_sample_*.xml`, including `wizards`, `automation`, `variables`,
`program_execution`) uses `rest` or `setVariable` — **the XSD alone is ground truth**
for these two step action types on this system.

### The `rest` element (`wizardRESTType`, XSD lines 1028–1069)

A `rest` element is one arm of the same `<choice>` that holds `template` (a leaf step has
`template` *or* `rest`, or neither). Children appear in this **fixed order** (all
optional unless noted):

| # | Element | Type | Notes |
|---|---------|------|-------|
| 1 | `httpMethod` | enum | **required**; `GET` \| `POST` \| `PUT` \| `DELETE` |
| 2 | `schemeName` | velocityString | defaults to the local z/OSMF instance |
| 3 | `hostname` | velocityString | ditto |
| 4 | `port` | velocityString | ditto |
| 5 | `uriPath` | velocityString | **required**; supports `substitution="true"` |
| 6 | `queryParameters` | velocityString | GET/POST only |
| 7 | `requestBody` | velocityString | |
| 8 | `expectedStatusCode` | xs:int | **required**; mismatch ⇒ step fails |
| 9 | `actualStatusCode` | `statusCodeType` | empty element; `mapTo="VAR"` (required attr) stores the real status code |
| 10 | `propertyMapping` | `variableNameType` | repeatable, unbounded — see below |
| 11 | `username` / `password` / `certificates` | velocityString | credentials for the call |
| 12 | `requestHeaders` | velocityString | single string; exact wire format not defined by the XSD |
| 13 | `pollCountMaximum` / `pollWaitTime` / `pollExitCondition` | | polling loop; `pollExitCondition expectedValue="..."` wraps a property name |

**`propertyMapping` shape (the big correction).** `variableNameType` (XSD line 1126) is
*simpleContent*: the **element content is the source property in the response body** and
the `mapTo` attribute is the target variable. There is **no** `propertyMappings` wrapper
and **no** `mapFrom` attribute:

```xml
<propertyMapping mapTo="INFO_VERSION">api_version</propertyMapping>
```

### The `setVariable` element (`setVariableType`, XSD lines 1405–1414)

`setVariable` is **not a step body** — it is a repeatable child of a leaf step that comes
**after** the `template`/`rest` choice (XSD line 1019, `maxOccurs="1500"`). A step may
carry `setVariable` with no `template` and no `rest` at all.

`setVariableType` is *simpleContent* extending `velocityString`: the **element content is
the value expression** (no `<expression>` child), with attributes:

- `name` (required) — target variable, must reference a declared variable
  (enforced by an XSD `keyref`, line 132)
- `scope` — fixed to `instance` in practice (`setVariableScopeType`, line 812)
- `substitution` — inherited from velocityString; set `"true"` to expand
  `${instance-VAR}` references in the content

```xml
<setVariable name="REPORT_NAME" substitution="true">inventory-${instance-INFO_VERSION}</setVariable>
```

Uniqueness constraint (XSD line 72): within one step, `setVariable` entries must be
unique across (name, scope).

## Error archaeology (register loop on ZOS31)

| # | Error | Cause | Fix |
|---|-------|-------|-----|
| 1 | `IZUWF8017E: Property mapping error for property "api_version". Attempt to parse the mapping property failed.` | `propertyMapping` content is **not** a bare property name — it is a bracket-notation JSON path evaluated against the response body. | `["api_version"]` for a JSON-object property; `[0]["jobid"]` would address an array element; `[]` maps an entire text/plain body. Documented in IBM's "How to use z/OSMF Workflow REST steps" community blog (Qi Li, 2024). Registration succeeded on attempt 2. |
| 2 | `IZUWF9999E: ... "No subject alternative names matching IP address 9.12.19.209 found"` (getInfo run) | With no `hostname` in the XML, the engine self-calls **using the host from the URL the client used to start the step**. Our Zowe profile connects by IP; the server certificate carries only the DNS name. | Drive `create`/`start` via the hostname (`--host zos31.pok.stglabs.ibm.com`) — the self-call then matches the certificate SAN. No XML change needed (see #3/#4 for why hardcoding the host is worse). |
| 3 | `IZUWF8053E: The elements "username" and "password" are required when the HTTPS scheme is specified.` | Tried `<schemeName>https</schemeName>` + `<hostname>` to fix #2 in the XML. Explicit https makes the engine treat the target as a *remote* z/OSMF and demands credentials. | Abandoned this route (see #5): same-instance calls should omit scheme/host/port entirely. |
| 4 | `IZUWF8052E: The elements "schemeName", "hostname", and "port" must be provided as a group.` | Tried `<hostname>` alone (hoping to keep default scheme + inherited auth). Not allowed. | Same as #3 — omit the whole group. |
| 5 | `IZUWF9999E: ... log in as user andre ... failed with response code 401 ... IZUG410E` | With explicit scheme/host + credentials (via variables **and** hardcoded literals; lowercase **and** uppercase user), the engine's remote-login handshake gets 401 from its own instance — while the same credentials succeed via `POST /zosmf/services/authenticate` from the workstation and from the host shell (with and without the CSRF header). Engine-internal login path restriction; not resolvable as an unprivileged user. | Confirmed the credentialed-remote route is a dead end on this system; the `--host` fix from #2 makes it unnecessary. |

Working combination: **omit scheme/hostname/port/username/password in the XML and
connect by DNS hostname when starting steps.** `requestHeaders` takes a JSON object
string, e.g. `{"Content-Type":"text/plain"}` — required for the job-submit PUT (the
jobs API needs a text/plain body).

## Evidence of the verified run (ZOS31, 2026-07-09)

Workflow instance `2d5f608c-cc0f-4311-9f7b-4cc12d648a5a`, created and driven entirely
with Zowe CLI (`--host zos31.pok.stglabs.ibm.com`). Final `--steps-summary-only`:

```text
name        state    stepNumber misc
getInfo     Complete 1          HTTP 200
deriveNames Complete 2          N/A
submitProbe Complete 3          HTTP 201
writeReport Complete 4          JOB07085
```

Instance variables after the run (`returnData=variables`):

```text
name         value
----         -----
INFO_VERSION 1            <- captured by getInfo propertyMapping ["api_version"]
REPORT_NAME  inventory-1  <- derived by deriveNames setVariable
PROBE_JOBID  JOB07083     <- captured by submitProbe propertyMapping ["jobid"]
PROBE_STATUS 201          <- captured by submitProbe actualStatusCode mapTo
```

Spool of the writeReport shell-JCL job (`zowe jobs view all-spool-content JOB07085`):

```text
===== z/OSMF SELF-INVENTORY =====
z/OSMF API version : 1
Report name        : inventory-1
Probe JOBID        : JOB07083
Probe HTTP status  : 201
=================================
SUCCESS: variables flowed across step types
```

Every value in the report was produced by a different step type (rest capture,
setVariable derivation, rest job-submit) and consumed by the final shell-JCL template —
the cross-step variable flow the artifact set out to prove. The probe job JOB07083
(IEFBR14, submitted *by the workflow engine* through the jobs REST API) ended CC 0000.

### Open questions the XSD cannot answer (resolved by the register/run loop)

1. **`propertyMapping` content syntax for nested JSON** — both of our captures
   (`api_version` from `/zosmf/info`, `jobid` from the job-submit response) are
   top-level scalars, so plain property names should suffice.
2. **`requestHeaders` wire format** — needed only if the PUT job-submit requires an
   explicit `Content-Type: text/plain`; fallback is the status-code-only GET probe.
3. **Whether same-instance `rest` calls inherit the workflow's authentication** or
   require explicit `username`/`password` elements. First attempt omits them.
4. **Whether a setVariable-only step is startable** via
   `zowe zos-workflows start workflow-step`; fallback is attaching the `setVariable`
   to the preceding rest step (legal per XSD ordering).
