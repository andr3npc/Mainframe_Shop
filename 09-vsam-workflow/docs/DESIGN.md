# Design — z/OSMF VSAM Provisioning Workflow

## Approach

Three flat leaf steps in one workflow definition. Flat because a step
that carries `weight`/`skills`/`autoEnable`/`canMarkAsFailed` is an
executable leaf and must be followed by an action element — it cannot
also nest substeps. Grouping buys nothing here.

| Step | Action | Success judged by |
|------|--------|-------------------|
| `define-ksds` | `fileTemplate` (JCL) → IDCAMS `DEFINE CLUSTER` | job return code |
| `verify-ksds` | `inlineTemplate` (TSO-REXX) → `LISTCAT` | `successPattern` regex on output |
| `delete-ksds` (optional) | `inlineTemplate` (JCL) → IDCAMS `DELETE ... PURGE` | job return code |

The DEFINE JCL is a **separate template file** (`vsam-define.template`)
referenced by `fileTemplate` with a USS path — the same structure IBM's
`adduser` sample workflows use. The JCL can be edited and re-uploaded
without touching (or re-validating) the workflow XML.

## Schema rules that matter (each learned from a validator error)

- A step's action is exactly one of `template` / `rest` / `setVariable`.
  There are no `rexx`, `shell`, or `inline` elements in the schema.
- `submitAs` is a child element of `template` (values `JCL`,
  `shell-JCL`, `TSO-REXX`), not an attribute.
- `successPattern` is **required** for `TSO-REXX` (synchronous TSO
  execution, success = regex match on output) and **rejected** for
  `JCL`/`shell-JCL` (asynchronous job, success = return code).
- Instance variables must be written `${instance-NAME}`. A bare
  `${NAME}` is not an error — it just passes through literally, which
  is worse.
- `<default>` only pre-fills the z/OSMF UI prompt. Creating an instance
  headless (REST/Zowe CLI) leaves variables null unless `--variables`
  is supplied at create time.
- `description`/`instructions` are rich-text fields: a literal `<`
  starts a markup tag, so element names in prose must be escaped or
  paraphrased.

## Encoding matrix (the silent killer)

| File | Upload | Why |
|------|--------|-----|
| `vsam-create.xml` | `--binary` | z/OSMF reads the XML as ASCII. A text upload transcodes to EBCDIC and the parser dies with "Content is not allowed in prolog" (EBCDIC `<` = 0x4C reads as `L`). |
| `vsam-define.template` | text (default) | z/OSMF reads `fileTemplate` targets as EBCDIC — matching the untagged-EBCDIC `.template` files shipped in `/global/zosmf/<sys>/data/workflows`. |

Related trap when *searching* the system workflow directory: the
shipped `.xml` files are tagged ISO8859-1 with autoconversion off, so
an EBCDIC-mode `grep` sees garbage and silently misses them. Convert
first: `iconv -f ISO8859-1 -t IBM-1047 file | tr '>' '\n' | grep ...`
(the `tr` also defeats grep's line-length limit on single-line XML).

## VSAM specifics

- `DEFINE CLUSTER ... INDEXED` with explicit `DATA`/`INDEX` component
  names (`<dsn>.DATA` / `<dsn>.INDEX`). The cluster name is capped at
  38 characters in the variable definition so the component names stay
  within the 44-character dataset name limit.
- `MAX_RECLEN` must be ≥ `AVG_RECLEN` and > `KEY_OFFSET + KEY_LENGTH`
  (the whole key must fit inside every record).
- Initial load: `REPRO` into an empty KSDS requires input in ascending
  key order. `LOADKSDS.jcl` loads 10 fixed-80 records (key = cols 1-8,
  spaced by 10 to leave insert room) and then `PRINT ... COUNT(3)` to
  prove the records come back through the index, not just that the
  load RC was zero.

## What could go wrong / edge cases

- Re-running `define-ksds` when the cluster exists fails with IDCAMS
  "duplicate name" (RC 12). By design: this workflow provisions; it
  does not silently replace. Use the optional `delete-ksds` step first.
- `--overwrite` on `create workflow-from-uss-file` fails once an
  instance has started a step; create a fresh instance (new key)
  instead of reusing the name.
- On a busy shared LPAR, TSO-REXX steps started via CLI can sit in
  `Submitted` for a long time (async TSO queue). The z/OSMF web UI
  performs them in the user's ISPF-gateway session immediately.
