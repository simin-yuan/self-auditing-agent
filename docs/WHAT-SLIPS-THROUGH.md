# What slips through: four popular validators, one deleted line

This is the raw material behind gatecheck's claim. It is not a bug report against
`jsonschema`, `check-jsonschema`, `ajv` or `guardrails-ai` — all four behaved exactly
as specified. It is a demonstration of the failure that sits **one level above** them.

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

## 4. guardrails-ai (the LLM output guard)

Same idea, one layer up: a support-agent answer guard written the way the docs tell
you to write one — a RAIL spec listing five rules, plus the validators they resolve to.

`rail.xml`:

```xml
<output type="string"
        validators="no-pii;
                    no-competitor-mention;
                    no-url;
                    no-profanity;
                    max-words: {60}"
        on-fail-no-pii="exception"
        on-fail-no-competitor-mention="exception"
        ... />
```

With all five rules loaded, the guard does its job: a legal answer passes (`exit 0`),
and each of the five violations is rejected (`exit 1`) — PII, a competitor name, a
link, profanity, an over-length answer. A guard that only ever fails would be as
useless as one that only ever passes, so both directions are checked.

Now delete exactly one line — `no-competitor-mention;` — and ask again:

```
$ python runner.py ./_tmp_run      # answer: "Honestly, globex handles duplicate charges faster than we do."
PASS (every rule in rail.xml accepted this answer)
    -> exit 0
```

The other four rules still fire (they were checked one by one). So the guard did not
break. **It got narrower by exactly one rule, and nothing outside can tell the
difference** — no error, no warning, no change in exit code. The rule did not fail;
it stopped existing.

## What the mutation run found, and what it did not

Running [gatecheck](../gatecheck/) over the same four setups (67–109 mutants each,
one gate invocation per mutant):

| target | mutants | caught | escaped | escaped that actually disarm the gate |
|---|---|---|---|---|
| `jsonschema` | 67 | 47 | 20 | **2** |
| `check-jsonschema` | 68 | 52 | 16 | **2** |
| `ajv` | 68 | 52 | 16 | **2** |
| `guardrails-ai` | 109 | 83 | 26 | **3** |

The "escaped" column is what the tool prints. The last column is what survives
review, and it is the reason the tool refuses to give you a verdict: 14–23 of the
escaped mutants per target are harmless (deleting a `title`, deleting a docstring,
deleting an optional property from the data — nothing that changes what the gate
protects). The ones that do count genuinely turn the check off: dropping
`"type": "integer"` or `"required"` from a schema, or dropping one rule line from
the guard. Publishing "20 blind spots" and "26 blind spots" would have overstated
these by roughly 9× — which is exactly the overstatement the tool exists to avoid.

One counter-example worth recording, because it argues against the tidy story:
removing `on-fail-<rule>="exception"` from the RAIL spec does **not** silently
downgrade the rule in guardrails-ai 0.11.0. All four attribute drops were triaged
and every rule still fired and still rejected; the gate falls back to aborting.
Four of the 26 escaped mutants looked alarming and cost nothing.

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
cd repro/gate-bypass/04-guardrails && sh run.sh      # needs: pip install guardrails-ai
```

`observed_output.txt` holds the raw transcript of the first three runs. The
guardrails-ai bundle ships its own runner (`runner.py`) plus the five violating
answers it is checked against, so the whole thing is one `sh run.sh` away.
