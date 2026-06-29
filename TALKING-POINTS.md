# Talking Points — explaining the portfolio in a technical interview

Audience: senior z/OS systems programmers. This is a study sheet, not a
script. For each artifact: the one-line pitch, the concept it proves, the
deep technical points an interviewer will probe, and the **war story** —
the bug or gotcha that came up building it. Lead with the war stories; they
show *method*, which is what separates a sysprog from someone who memorised
macros.

Everything here was assembled, linked, and **run on a real z/OS system** —
see each artifact's `docs/DESIGN.md` for captured output.

---

## The 30-second pitch

> Eight HLASM artifacts covering the systems-programming toolkit: macro
> engineering, walking live control blocks, dynamic allocation through the
> JES2 subsystem, ESTAE recovery with SDWA analysis, SMF record mapping,
> IPCS dump analysis, plus the modern side — Ansible/z/OSMF automation and
> parm-driven feature-flag routing. All written to z/OS conventions
> (AMODE 31, standard linkage, IBM DSECTs, never a hardcoded offset) and
> all verified on a real system — including two I had to debug because they
> compiled but didn't actually work.

## The 2-minute narrative

I built this to read like production code in a review, not just to run.
The through-line is the **recovery / diagnosis** skill set: artifact 2
reads control blocks the way you'd read them in a dump; artifact 4 reads
the SDWA live, at the moment of failure, the same fields you'd read in a
dump; artifact 6 *produces* a controlled dump to analyse with IPCS. Around
that core sit the bread-and-butter sysprog services — dynamic allocation,
QSAM, SMF mapping — and then the modernization angle: driving a mainframe
build from Ansible over z/OSMF REST, and a feature-flag pattern for z/OS
batch. The thing I'm proudest of isn't any one program; it's that I
verified all of them on a live system and found that two imported pieces
were committed broken and looked fine. "It compiled" is not "it works."

---

## 01 — Personal Macro Library

**Pitch:** A curated set of structured-programming and utility HLASM
macros — `@ENTER`/`@LEAVE`, `@IF`/`@ELSE`/`@ENDIF`, `@DO`/`@ENDDO`,
`@HEXOUT`, `@PCALL`.

**Concept it proves:** The macro language as a meta-language — conditional
assembly, `&SYSNDX` for unique label generation, `GBLA` counters for
nesting, `MNOTE` for compile-time diagnostics.

**Deep points:**
- `@ENTER`/`@LEAVE` are standard OS entry/exit linkage: `STM 14,12,12(13)`,
  chain a save area, `USING &SYSECT,&BASE`. Deliberately **non-reentrant**
  (static save area) — a documented choice, not an oversight.
- `@IF`/`@DO` generate unique labels off `&SYSNDX` so the constructs nest;
  a `GBLA` counter tracks nesting depth; `@XINVB` inverts the branch
  condition so the generated code skips *around* the block.
- `@HEXOUT` converts binary to printable EBCDIC hex with the classic
  `UNPK` + `TR` translate-table technique, in macro-time chunks of ≤7 bytes
  (the `UNPK` width limit); `MODE=DEFINE` emits the shared table once.

**War story — the addressability cascade.** Calling `@ENTER CSECT=name`
when `@ENTER` has no `CSECT=` keyword produced `ASMA017W`, then
`USING ,12` (empty operand, `ASMA074E`), then a *flood* of `ASMA307E
No active USING` at every label, then `ASMA044E` on `END`. One broken
`USING` throws errors at every *use*, far from the real defect. The fix:
code `CSECT`/`AMODE`/`RMODE` before a **bare** `@ENTER`, because the macro
bases addressability off the active `&SYSECT`. Lesson: in HLASM, read the
*first* error, not the hundredth.

---

## 02 — Control Block Walker

**Pitch:** Walks the live chain PSA → CVT → ASCB → TCB from address 0 and
prints key identity fields from each block.

**Concept it proves:** z/OS internals and DSECT discipline — `IHAPSA`,
`CVT`, `IHAASCB`, `IKJTCB`. Never a hardcoded offset.

**Deep points:**
- `FLCCVT`→CVT, `PSAAOLD`→current ASCB, `PSATOLD`→current TCB. Each pointer
  and eyecatcher is **validated before it's dereferenced** — a zero
  pointer or bad `ASCB` eyecatcher returns RC 4, it does not abend.
  Defensive control-block walking is the whole point.
- The below-the-line DCB trick: the CSECT is `RMODE ANY`, so the assembled
  DCB model loads above 16M, and **OPEN cannot open an above-the-line DCB**
  (`IEC190I`, `DCBOFOPN` never comes on). So `GETMAIN LOC=BELOW`, copy the
  model down, open the copy; confirm with `TM DCBOFLGS,DCBOFOPN`.

**War story / framing:** this is "reading a dump, but in code." It's the
same skill as walking save-area chains and control blocks in IPCS — just
live. The DCB-above-the-line issue is the same family as the S0C4-on-OPEN
trap in artifacts 3 and 5.

---

## 03 — JES2 SYSOUT Scraper

**Pitch:** Dynamically allocates a dataset via SVC 99 (`SUBSYS=JES2`),
reads it with QSAM, and writes matching lines to a dynamically-allocated
SYSOUT — pattern and dataset both from the EXEC `PARM`.

**Concept it proves:** Dynamic allocation, the JES subsystem interface,
QSAM — real sysprog work tied to a JES background.

**Deep points:**
- SVC 99 by hand: the request block (`S99RB`), the text-unit pointer list
  (`S99TUPL`), and the text units (`S99TU`: key / number / length /
  parameter). You build all three.
- **The `S99RB` must be `DS 0F`-aligned.** The header is 8 bytes, then
  `S99TXTPP` (an `A`-adcon) at offset 8. `DC A` self-aligns to a fullword,
  so an unaligned RB pads and shifts `S99TXTPP` to offset 9 → SVC 99 reads
  the text-unit-list pointer from the wrong place → **S0C4**. The
  `X'80',AL3(rb)` pointer idiom also needs the module below 16M (RMODE 24)
  or the 3-byte address truncates.

**War story — `EX` with R0 is a no-op modifier.** `EX R0,target` executes
the target *unmodified* (R1 field of 0 is the special "execute as-is"
case), so `EX R0,(MVC dst(0),src)` moves **1 byte**, not the intended
length. Symptom: a parsed string silently truncated to its first byte.
Always use a non-zero register for the `EX` length.

---

## 04 — ESTAE Recovery Demo  *(strongest piece — lead with this)*

**Pitch:** Deliberately abends (S0C7), recovers in an **ESTAEX** routine,
reads the SDWA, and then **retries** or **percolates** depending on the
EXEC `PARM` — no relink to switch.

**Concept it proves:** Recovery-routine design and SDWA analysis. This is
the debugging skill set turned inside-out: the same SDWA fields you read in
a dump, read **live, in code, at the moment of failure**.

**Deep points:**
- **ESTAEX, not ESTAE:** the modern form, AMODE-31 / cross-memory clean.
  `TERM=YES` so the exit also covers task / address-space termination.
- The recovery exit's RTM entry protocol (it does **not** use `@ENTER`):
  R0 = SDWA indicator, R1 → SDWA, R2 → your `PARAM` area, R13 → RTM's
  200-byte work area, R15 = entry. I pass the mainline base register
  through `PARAM=` and reload it in the exit, so one `USING` re-establishes
  addressability to the whole program.
- `SETRP` drives the outcome: `RC=4` + `RETADDR` + `RETREGS=YES` to retry
  (RTM restores the registers from `SDWAGRSV`, so the base and save area
  are valid at the resume point); `RC=0` to percolate; `FRESDWA=YES`.
- Fields read: `SDWAABCC` (completion code — observed `840C7000`: RTM flags
  + the `0C7`), `SDWAEC1` (the PSW at the error; its low 31 bits are the
  failing instruction address), `SDWAGRSV` (the GPRs at the time of error).

**War story — the no-SDWA test must be `R0 == 12`, not "nonzero".** First
working build percolated *both* ways and never printed the SDWA. The exit
was being entered with **R0 = 16**, and my test treated any nonzero R0 as
"no SDWA," so it diverted to the percolate-only path. Only `R0 = 12` means
no SDWA; RTM passes other codes (0, 16, …) *with* a valid SDWA in R1. I
instrumented the exit to `WTO` R0 and R1, saw `R0=00000010` and
`R1=109016D8` (a real address → SDWA present), and changed the test to
`C R0,=F'12'`. That's the whole interview in one story: **hypothesis →
instrument → observe → fix**, not guessing.

**Likely follow-ups:** ESTAE vs ESTAEX vs FRR? When do you retry vs
percolate? What's in the SDWA? Why `RETREGS=YES`? What if there's no SDWA?

---

## 05 — SMF Type-30 Reporter

**Pitch:** `MKSMF30` writes synthetic type-30 subtype-5 (job-termination)
records; `SMFRPT30` reads them with QSAM and reports job CPU / elapsed.

**Concept it proves:** SMF record mapping, **self-defining sections via
triplets**, multi-DSECT addressability — ties to a JES/SMF background.

**Deep points:**
- A type-30 record is self-defining: a fixed header carries **triplets**
  (offset / length / count) that locate each optional section. You never
  hardcode an SMF offset — read the section's `xOF`, add the record base,
  `USING` the DSECT there. `IFASMFR (30)` gives `SMFRCD30` / `SMF30ID` /
  `SMF30CAS`. A zero offset means the section is absent — skip it (`BZ`),
  don't dereference null.
- The arithmetic: CPU = `(SMF30CPT + SMF30CPS)/100`, elapsed =
  `SMF30TME − SMF30RST`, formatted with `CVD` + `ED`.
- Linked **RMODE 24** on purpose (QSAM DCB) — the S0C4-on-OPEN fix.
- Output is `RECFM=VB`, not VBS: spanned records don't support `MACRF=PM`
  move mode (it leaves the PUT-routine pointer zero).

**War story — one bug masking another.** The build had two defects, and the
first hid the second: an `@ENTER` misuse caused the addressability cascade
(see artifact 1), and *underneath it* was a `USING SMF30ID,R82` typo (`R82`
undefined). The `ASMA307E`s from the typo only appeared once the cascade
cleared. Lesson: fix the first defect and **re-assemble** before chasing
the rest of the list.

---

## 06 — IPCS Dump Practice

**Pitch:** Builds eyecatcher'd storage structures and a control-block
chain, then forces a **U0013** dump to analyse with IPCS.

**Concept it proves:** Dump analysis / problem determination — `SETDEF`,
`SUMMARY`, `REGS`, `WHERE`, `LISTDUMP`, `FIND`, `CBFORMAT`. The *producer*
side of debugging, and the mirror of artifact 2 (which reads control blocks
in code, where this one lays them out to be found in a dump).

**Deep points:**
- Eyecatchers (`DUMP`, `ENTRY0`–`ENTRY9`, `CTL1`/`CTL2`/`CTL3`) and forward
  / back pointer chains are placed so each IPCS command has an obvious
  target — `FIND 'CTL1'`, then follow the forward pointer to `CTL2` to
  `CTL3`, verify the back pointers. `ABEND 13,DUMP` produces the dump.

**War story — "it compiled" wasn't "it works."** When I verified it, it
**didn't even assemble**: no register equates at all (`R0`–`R15`
undefined → a wall of `ASMA044E`), a fragile inline literal continuation
whose `X` didn't land in column 72 after upload (`ASMA063E`), and records
after `END` starting a phantom second assembly (`ASMA140W`). I added the
equates, moved the strings to named constants, and trimmed past `END`. Now
`BUILDDMP` is CC 0000 and `RUNDUMP` abends U0013 as designed. The takeaway:
this had been committed as "working"; only building it on a real system
proved otherwise — which is exactly why I verified the whole portfolio.

---

## 07 — Ansible Automation (z/OSMF REST)

**Pitch:** An Ansible playbook drives a HLASM assemble/link through the
z/OSMF REST API — upload, submit, poll, fetch output, gate on return code.

**Concept it proves:** DevOps on z/OS — z/OSMF REST, automation with
credentials kept out of source.

**Deep points:**
- `ansible.builtin.uri` against z/OSMF: REST file upload → `PUT` the job →
  poll `until status == OUTPUT` → pull `SYSTSPRT`/`JESMSGLG` → **fail the
  play** unless the return code is clean. The password comes from
  `$ZOS_PASSWORD`, never the repo.
- Framing: bringing a mainframe build into the same automation as the rest
  of the estate — a stepping stone toward CI/CD for HLASM.

**Note for honesty:** the compile JCL it drives is verified (CC 0000); the
full Ansible run needs a control host + credentials, so it's run by hand,
not in the repo. A production-grade version would use the IBM
`ibm.ibm_zosmf` collection rather than raw REST.

---

## 08 — Feature-Flag Routing

**Pitch:** One load module selects a **LEGACY** or **NEW** path from the
EXEC `PARM`, with no relink to switch — progressive delivery for z/OS
batch.

**Concept it proves:** Parm-driven routing / feature flags, and
**register-1 lifetime discipline**.

**Deep points:**
- Inspect the length-prefixed parameter area from R1, `CLC` the text
  against the flag value, branch, and `WTO` the route taken. Both paths
  return RC 0 — a feature flag selects *behaviour*, not pass/fail; the
  observable is the WTO, not the return code.

**War story — the dead flag (an R1 lifetime bug).** The original version
(misnamed `FLAGDB2`; it never had any DB2 in it) **always took the legacy
path** regardless of the flag. Why: `GETMAIN RU` returns the acquired
storage address in **R1**, and the EXEC parm pointer is *also* in R1 at
entry — the `GETMAIN` ran *before* the parm was read, so the code inspected
the freshly-zeroed work area, got length 0, and fell through to legacy
every time. Its "validated, RC 0" meant nothing, because both paths
returned 0 unconditionally. Fix: save R1 into a non-volatile register
*first*. Classic lesson: **R1 has a lifetime — any service that loads it
(GETMAIN, most macros) destroys the parm pointer** — and "it returns 0" is
not verification.

---

## Cross-cutting themes (for "tell me about your approach")

- **Conventions, everywhere:** AMODE 31, standard OS linkage
  (R13/R14/R15/R1), IBM-supplied DSECTs and macros, never a hardcoded
  control-block offset.
- **AMODE vs RMODE, and when RMODE 24 matters:** the QSAM artifacts (3, 5)
  are linked RMODE 24 on purpose, because OPEN's parameter list uses a
  24-bit `AL3(dcb)` address — let the module load above the line and OPEN
  faults S0C4. Artifact 2 instead keeps the CSECT RMODE ANY and copies the
  DCB below the line. Knowing *which* fix to reach for is the point.
- **Verification discipline:** "it assembled" ≠ "it works." Two artifacts
  (6, 8) were committed as working and were actually broken — one didn't
  assemble, one had a dead code path. Building and running on a live system
  is the only proof. Watch for the **stale-load-module trap**: an assembler
  warning drops the build to RC 8, `COND=(4,LE,ASM)` skips the link, and a
  rerun silently executes the *previous* load module and looks fine —
  always confirm BUILD = CC 0000 (link actually ran) before trusting a run.
- **Debugging method on a hostile system:** dumps are suppressed
  installation-wide and `TPUT` abends S15D, so I diagnose by bracketing
  with `WTO ... ROUTCDE=(11)` checkpoints and, when needed, instrumenting
  to print registers — hypothesis, instrument, observe, fix (see the
  ESTAE story).
- **HLASM column discipline:** code in cols 1–71, continuation indicator in
  col 72. The traps that bite: a comment bleeding into col 72
  (`ASMA144E`), and any record after `END` starting a phantom assembly
  (`ASMA140W`).

## Skills matrix

| Competency | Artifact(s) |
|---|---|
| Macro language / conditional assembly | 1 |
| Standard OS linkage, save-area chains | 1, all |
| Control-block navigation, DSECT discipline | 2 |
| AMODE/RMODE, above/below the line, OPEN | 2, 3, 5 |
| Dynamic allocation (SVC 99), JES SSI | 3 |
| QSAM I/O | 3, 5 |
| Recovery routines (ESTAEX), SDWA analysis | 4 |
| SMF record mapping, self-defining sections | 5 |
| Dump analysis (IPCS) | 6 |
| DevOps / z/OSMF REST / Ansible | 7 |
| Parm-driven routing, R1 discipline | 8 |
| Live-system debugging & verification | all |

## Quick-fire questions to rehearse

- *What happens, step by step, when your program abends?* → program check →
  RTM → your ESTAEX gets control with the SDWA → read `SDWAABCC`/`SDWAEC1`
  → `SETRP` retry or percolate.
- *How do you read a control block safely?* → IBM DSECT, validate the
  pointer and eyecatcher before dereferencing, mind AMODE/RMODE.
- *Why RMODE 24 on the QSAM programs?* → OPEN's `AL3(dcb)` is 24-bit; above
  the line it truncates → S0C4.
- *Reentrant or not, and why?* → non-reentrant here (static save areas), a
  documented simplicity choice; I can explain what RENT would change.
- *Tell me about a bug you found.* → the ESTAE `R0==12` story or the
  FEATFLAG R1/GETMAIN story — both show method, not luck.
