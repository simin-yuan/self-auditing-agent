# Blind spots in my own gate (a gatecheck health report)

**The existence of this file is what the archive claims: anything that says it can be checked must first check itself.**

Method: `gatecheck` runs automated mutation testing against my own 25-rule validator — it cuts legal
input into 175 variants, drives each one at the gate, and watches whether the gate stops it.

```bash
python gatecheck/gatecheck.py \
  --gate "python repro/validate_meta_model.py {target} --source repro/fixtures/valid-source" \
  --target repro/fixtures/valid-meta-model \
  --report gatecheck-report.json
```

**Result: 175 mutants, 97 caught, 78 missed (44%).**

Below are the ones I reviewed one by one and judge to be **real defects** (most of the rest are
mutations that are semantically legal, and do not count as defects).

---

## Defect 1 (the worst): delete the declaration and the check is bypassed

```
missed  drop-line:functional-inventory.md:9  ->  "- 交互类型: non-interactive"
```

The original rule (`validate_meta_model.py:282`) says:

> **If** a function declares itself `non-interactive`/`hybrid`, **then** it must be registered in
> `non-menu-function-index.md`.

The problem is that this is a **conditional rule, and the condition is supplied by the party being
inspected**.

So the cheapest way around it is not to file the registration — it is to **delete the declaration line**.
Once it is gone the antecedent is false, so the consequent is not required, **and the gate says nothing at all.**

**Why this is a real defect**: it turns a requirement into an opt-in. A check that only takes effect
once you admit guilt is not a check. In practice this means a background scheduled task can simply not
write an interaction type into the inventory, and it will never enter any register — with the gate green
the whole way.

**Direction of the fix** (not implemented yet, see "Not finished"): make "every function must declare an
interaction type" an unconditional rule; that is, first require the type to be a legal, mandatory enum
value, and only then talk about downstream constraints. **Whether a criterion applies must not be decided
by the party under inspection.**

---

## Defect 2: every subsection of an implementation chain can be empty

```
missed  drop-line:function-chain-index.md:27/29/31/33/35/37  ->  "- 略"
```

The gate checks that 8 subsections such as `### Requirement Link` **have their headings**,
but it **does not check whether the subsections contain anything**.

Result: all 8 headings with nothing underneath, and the gate still lets it through. **"The structure
is complete" was taken for "the content is there".**

The general shape of this defect: **an existence check standing in for a completeness check.**
A file on disk is not the same as something in the file; having a field is not the same as the field
being filled in.

---

## Defect 3: an ID that is defined but referenced by nobody — renaming it leaves no trace

```
missed  break-ref:business-architecture.md:MENU-M1 -> MENU-MZ
missed  break-ref:business-architecture.md:ENTRY-E1 -> ENTRY-EZ
missed  break-ref:domain-model.md:OBJ-1       -> OBJ-Z
```

The gate's reference check is **one-directional**: it checks that "a referenced ID has a definition",
but not that "a defined ID is referenced by anything".

So a definition with no referrers can be renamed, deleted, or misspelled, **and the gate will not react**.
(Note: in this minimal baseline those IDs happen to have no referrers, so the miss is "structurally correct
but undetectable" — what it exposes is **the gate having no reverse entry point**, not a typo made this round.)

For contrast, the validator **does** have the equivalent check for behaviours (the reverse references in
`reference_index.py`), but the main validator does not. **The same kind of rule has different maturity in
different files.**

---

## Defect 4: duplicate headings cannot be detected

```
missed  dup-id:*.md  x25 (copy each file's H1 heading into a second-level heading)
```

A heading is not an ID, so "the same heading appears twice" is covered by no rule. Harmless this round,
but if any downstream tool uses headings as anchors, duplicate headings will point an anchor at the wrong
section.

---

## I do not call all 78 of these defects

In fairness: **most of the 78 misses are semantically legal mutations**, for example:

- `drop-line` removing placeholders such as `- 略` — the content was meaningless to begin with;
- `dup-id` copying an H1 heading — a heading is not an ID, so there is no conflict;
- `empty-file` clearing a file that "only needs to exist" — the gate never intended to verify its content.

Treating "the mutation was not caught" as identical to "the gate has a bug" is **passing quantity off as
quality**. So I went through them one by one, and only the 4 kinds above are cases that genuinely should
have been caught and were not.

**Which is exactly where gatecheck's role becomes clear: it does not give you a verdict, it gives you a
list.** It turns "I think my gate is strict" into "I know it does not react to these 78 rewrites, and 4
kinds among them are real problems".

---

## Not finished (the part I do not pretend about)

- **Not one of the 4 defects above has been fixed.** This file is a **diagnosis**, not a repair log.
  The fix will be a separate volume, and it must carry a "re-run gatecheck after the fix; missed went
  from 78 down to N" comparison.
- The baseline this round is the minimal legal input **I constructed** (`make_valid.py`); it only proves
  "the gate does not false-positive on a minimal legal input". **It does not prove "the gate can accept a
  real project".** The inputs from the ten-odd real repositories have not been run, because the original
  repository's meta-model files are incomplete.
- gatecheck has only 7 mutation operators, so coverage is limited (no value-level, type-level, or
  cross-file semantic mutation).

**All three of the above are debts, not disclaimers.**
