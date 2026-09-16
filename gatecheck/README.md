# gatecheck

**Does your quality gate actually reject anything?**

The most common failure of a validator, a CI check, or a linter is not that it has a bug.
It is that **it has never rejected anything — while everyone assumes it is protecting them.**

Your CI is green. That may mean your code is clean. It may also mean the check never ran.

`gatecheck` answers the question nobody asks until it is too late: **if I feed this checker something it is supposed to reject, does it reject it?**

## What it does

Give it two things:

- a **gate command** — anything that exits non-zero to mean "reject"
- a **baseline input** — something that currently passes that gate

It mutates the baseline N ways, **re-runs your gate once per mutant**, and reports which mutations the gate caught and which it let through.

```bash
gatecheck --gate "python validate.py {target}" --target ./my-data
```

```
baseline  : exit 0   ✅ passes
mutants   : 175
      caught  drop-file:schema.md
      ★ MISSED  drop-line:rules.md:12
      ★ MISSED  break-ref:domains.yaml:OBJ-1->OBJ-Z
...
caught 97 / 175
verdict: your gate did not react to 78/175 mutations — it has blind spots.
```

## What it does NOT do

**It does not give you a verdict. It gives you a list.**

A missed mutant is **not** automatically a defect — some mutations are semantically harmless.
`gatecheck` moves you from *"I assume my gate is strict"* to *"I know it does not react to these 78 edits, and now I have reviewed them."*

Whether a miss is a bug is a judgement call, and that judgement is deliberately left to you.

## Mutation operators

| Operator | What it does |
|---|---|
| `drop-file` | delete a whole file |
| `empty-file` | blank a file |
| `drop-section` | delete a markdown section / config block |
| `drop-line` | delete lines one at a time |
| `blank-value` | keep `key: value` but empty the value |
| `break-reference` | change one character of an identifier, creating a dangling reference |
| `dup-id` | duplicate an id, creating a duplicate definition |

## Exit codes

- `0` — every mutant was caught (no visible blind spot this round)
- `1` — some mutants were not caught; all of them are written to `--report`

## Zero dependencies

Standard library only. **A quality tool that makes you install a pile of things first does not end up on anyone's critical path.**

## Where it came from

This tool was not designed. It was forced out of me by pointing it at **my own** gate: 175 mutants, 78 slipped through, **4 of them real defects**.

The worst one: a rule whose trigger condition was supplied by the party being inspected — *"if you declare yourself non-interactive, you must be registered."* The cheapest way to bypass it was not to skip the registration. It was to **delete the four words `non-interactive`**. With the antecedent gone, the requirement never fires, and the gate says nothing.

> **A check that only applies once you admit guilt is not a check.**

Full diagnosis, including the defects I have *not* fixed yet: [`docs/BLIND-SPOTS.md`](../docs/BLIND-SPOTS.md).

---

## 中文

**你的门禁真的会拦吗？** 给它一个门禁命令和一份合法输入，它自动变异输入、逐个撞门禁，报告漏在哪。**它不给你判决，它给你清单。** 零依赖（只用 Python 标准库），退出码 0/1，可直接进 CI。

来历：我拿它去撞**我自己**的门禁，175 个变异漏过 78 个，其中 4 类是真缺陷。最狠的一条是「规则的触发条件由被检方自己提供，所以删掉四个字就能绕过全部检查」。

MIT
