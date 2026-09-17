# What slips through: three popular validators, one deleted line

This is the raw material behind gatecheck's claim. It is not a bug report against
`jsonschema`, `check-jsonschema` or `ajv` — all three behaved exactly as specified.
It is a demonstration of the failure that sits **one level above** them.

Every command and every line of output below was run on 2026-09-17 and is reproduced
verbatim. The fixtures are in [`repro/gate-bypass/`](../repro/gate-bypass/) — copy them, run them, disagree with me.

## Method

Three JSON Schema validators, the same schema, the same data, the same three steps:

1. original schema + valid data → the gate must pass
2. original schema + invalid data (`"timeout": "30"` — a string where the schema requires an integer) → the gate must reject
3. **the schema with one line deleted** (`"type": "integer"`) + the same invalid data → ?

Step 3 is the whole experiment. Nobody edits a schema by accident in a code review
that is watched by a human; they edit it in a hurry, and the CI is green afterwards
either way.

## 1. jsonschema (Python, draft 2020-12 reference implementation)

```
[1] original schema + valid data          exit 0
[2] original schema + invalid data        exit 1   30: '30' is not of type 'integer'
[3] one line deleted + same invalid data  exit 0   (nothing)
```

## 2. check-jsonschema (the pre-commit JSON/YAML gate)

```
[1] original schema + valid data          exit 0   ok -- validation done
[2] original schema + invalid data        exit 1   $.timeout: '30' is not of type 'integer'
[3] one line deleted + same invalid data  exit 0   ok -- validation done
```

## 3. ajv (JSON Schema, the JavaScript ecosystem default)

```
[1] original schema + valid data          exit 0   valid
[2] original schema + invalid data        exit 1   invalid
[3] one line deleted + same invalid data  exit 0   valid
                                                   strict mode: missing type "number" for keyword "maximum" at "#/properties/timeout" (strictTypes)
                                                   strict mode: missing type "number" for keyword "minimum" at "#/properties/timeout" (strictTypes)
```

ajv is the only one of the three that *knew*. It said so — on stderr, in a warning
nobody reads — and returned success. In CI, exit code is the only channel that is
actually watched.

## What the mutation run found, and what it did not

Running [gatecheck](../gatecheck/) over the same three setups (67–68 mutants each,
one gate invocation per mutant):

| target | mutants | caught | escaped | escaped that actually disarm the gate |
|---|---|---|---|---|
| `jsonschema` | 67 | 47 | 20 | **2** |
| `check-jsonschema` | 68 | 52 | 16 | **2** |
| `ajv` | 68 | 52 | 16 | **2** |

The "escaped" column is what the tool prints. The last column is what survives
review, and it is the reason the tool refuses to give you a verdict: 14–18 of the
escaped mutants per target are harmless (deleting a `title`, deleting an optional
property from the data — nothing that changes what the gate protects). Two per
target genuinely turn the check off: dropping `"type": "integer"`, and dropping
`"required"`.

A tool that reported "20 defects found!" here would be lying, and you would stop
believing it the second time you checked. So it reports the list and hands you the
judgement.

## Two more things the probes turned up

- **A typo in the schema is silent.** Rename `required` to `requird` in the schema
  and `check-jsonschema` exits 0 on data that is missing a required property —
  `ok -- validation done`. It validates nothing, and says it validated. (ajv, in
  strict mode, refuses: `unknown keyword: "requird"`. That is the correct behaviour.)
- **`--check-metaschema` cannot be combined with `--schemafile`**
  (`Error: --schemafile, --builtin-schema, and --check-metaschema are mutually
  exclusive`), so the one guard that would have caught the typo above cannot run in
  the same CI step as the validation it protects.

## Reproduce

```bash
cd repro/gate-bypass/01-jsonschema && sh run.sh     # jsonschema
cd repro/gate-bypass/02-check-jsonschema && sh run.sh
cd repro/gate-bypass/03-ajv && sh run.sh
```

`observed_output.txt` holds the raw transcript of these three runs.
