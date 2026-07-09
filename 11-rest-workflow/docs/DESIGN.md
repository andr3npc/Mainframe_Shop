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
