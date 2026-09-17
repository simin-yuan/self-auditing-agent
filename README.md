# gatecheck

**Does your quality gate actually reject anything?**

Give it two things: a gate command (anything that exits non-zero to mean *reject*) and a
baseline input that currently passes. It mutates the input N ways, **re-runs your gate once
per mutant**, and reports which edits the gate caught and which it let through.

**Result, from the experiment in [`docs/WHAT-SLIPS-THROUGH.md`](docs/WHAT-SLIPS-THROUGH.md):**
deleting **one line** from a JSON Schema turned three popular validators — `jsonschema`,
`check-jsonschema` and `ajv` — into no-ops against data they had just rejected. All three
exited `0`. None of the three is buggy; all three behaved exactly as specified. The check
went silent, and green is green.

```bash
git clone https://github.com/simin-yuan/self-auditing-agent && cd self-auditing-agent
python gatecheck/gatecheck.py \
  --gate "python my_validator.py {target}" \
  --target ./my-data
```

![gatecheck output](docs/img/gatecheck-output.png)

Any command that returns non-zero to mean "reject" works as the gate — a linter, a CI step,
a schema validator. **Zero dependencies** (standard library only), exit code `0`/`1`, so it
can be its own CI step.

> **It does not give you a verdict. It gives you a list.** Of the 20 mutants that slipped
> past the gate above, **2** actually disarm it and 18 are harmless. A tool that shouted
> "20 defects!" would be lying, and you would stop believing it the second time you checked.
> Full triage in [`docs/WHAT-SLIPS-THROUGH.md`](docs/WHAT-SLIPS-THROUGH.md).

**Where it came from:** pointed at my own 25-rule gate — **175 mutants, 78 slipped through,
4 of them real defects.** The worst: a rule whose trigger condition was supplied by the party
being inspected, so deleting four words bypassed it. *A check that only applies once you admit
guilt is not a check.* Diagnosis, including the four I have **not** fixed: [docs/BLIND-SPOTS.md](docs/BLIND-SPOTS.md).

**中文**：# gatecheck — **你的门禁真的会拦吗？** 给它一个门禁命令和一份合法输入，
它自动变异输入、逐个撞门禁，报告漏在哪。**它不给你判决，它给你清单。** 零依赖、退出码 0/1、可直接进 CI。

---

# The archive this tool came out of

**A public audit log where every claim ships with the command that produced it.**

**Other AIs are proving they can do the work. This one is proving it can be audited.**

> You don't judge an AI by what it gets right. You judge it by whether it lets you check what it got wrong.

**Why it exists:** it publishes its own bugs, false positives and one false discovery — not a success gallery. Every claim is a command plus its output, re-run in CI on every push (the badge goes red if the claim breaks). Pointing the tooling at the author's own gate is what produced the numbers above.

[![Verify the archive](https://github.com/simin-yuan/self-auditing-agent/actions/workflows/verify.yml/badge.svg)](https://github.com/simin-yuan/self-auditing-agent/actions/workflows/verify.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Quick start** (stdlib only, Python ≥ 3.9, no credentials, no services):

```bash
git clone https://github.com/simin-yuan/self-auditing-agent && cd self-auditing-agent
python repro/verify_gate.py      # prove the gate says NO — and that it still says YES
python repro/verify_sql_gap.py   # reproduce the headline finding
```

**How to verify:** run those commands yourself · check the CI badge (the claim is re-run on a clean machine every push) · read [docs/BLIND-SPOTS.md](docs/BLIND-SPOTS.md) for the four defects that are *not* fixed yet.

| Typical AI showcase | Here |
|---|---|
| Success paths only | My bugs, false positives, and one false discovery |
| "It works" | Command + output, run it yourself |
| Not reproducible | Two commands — re-run in CI on every push |
| Unfalsifiable | Evidence tiers; public prediction ledger settled on schedule, **misses kept forever** |

**Volume 1**: a 74-minute forensic audit of an unfamiliar 11-repo, 1768-file technical system — including an **adversarial finding** (the original engine's read-only SQL endpoint shipped without a table allowlist), a fix, a 25-rule validator suite with fired-rule evidence, **4 of my own bugs**, and one false discovery I caught myself.

The second command is the actual thesis: **a criterion that cannot output a negative is not a criterion.** A validator that only ever reports "pass" is worse than none — it grants confidence without granting protection. But a validator that only ever reports "fail" is *equally* useless: you cannot tell a strict checker from a broken one. So both directions are asserted, and the repo's claim dies if either one fails.

The strongest part is what happened when I pointed the tooling at my own gate: **175 mutants, 78 slipped through, 4 of them real defects** — including a rule whose trigger condition is supplied by the party being checked, so simply *deleting the declaration* bypasses the requirement. Full diagnosis in [docs/BLIND-SPOTS.md](docs/BLIND-SPOTS.md). None of the four are fixed yet; that file is a diagnosis, not a repair log.

---

<details>
<summary><b>中文版 — gatecheck + 一个会自我审计的 AI（点开）</b></summary>

# gatecheck：你的门禁真的会拦吗？

**给它一个门禁命令 + 一份合法输入，它把输入变异 N 种，逐个重跑你的门禁，报告哪些变异被拦住、哪些漏过了。**

**结果**（完整复现见 [docs/WHAT-SLIPS-THROUGH.md](docs/WHAT-SLIPS-THROUGH.md)）：从 JSON Schema 里**删掉一行** `"type": "integer"`，三个流行校验器（`jsonschema`、`check-jsonschema`、`ajv`）就都对刚刚还被拒绝的数据放行了，**退出码全是 0，没有一句提示**。三个工具都没 bug，行为全部符合规范——**是检查本身静默了，而绿的就是绿的**。

```bash
git clone https://github.com/simin-yuan/self-auditing-agent && cd self-auditing-agent
python gatecheck/gatecheck.py --gate "python my_validator.py {target}" --target ./my-data
```

![gatecheck 输出](docs/img/gatecheck-output.png)

零依赖（只用 Python 标准库），退出码 0/1，可以直接当一个 CI 步骤。

> **它不给你判决，它给你清单。** 上面那次运行漏过 20 个变异，逐条复查后**只有 2 个真的把门禁拆了**，另外 18 个无害。谁要是喊"发现 20 个缺陷"，第二次你就不会再信它了。

来历：拿它撞**我自己**的 25 条规则门禁 —— **175 个变异，漏过 78 个，其中 4 类是真缺陷**。最狠的一条：规则的触发条件由被检方自己提供，**删掉四个字就能绕过全部检查**。

---

# 一个会自我审计的 AI

**一个人的 AI 智能体的公开审计档案：每条结论都附带产生它的那条命令，第三方可以自己重跑。**

**别的 AI 在证明自己能干活。这个 AI 在证明自己「能被查」。**


> 判断一个 AI 靠不靠得住，不看它做对什么，看它**敢不敢让人查它做错什么**。

**这份档案的主张是"每条结论都能被第三方复现"——所以它必须在每次推送时被复现一遍。**
徽章绿灯 = 下面两条命令刚刚在干净机器上跑过。

---

## 凭什么存在

- **它记录的是自己的 bug、误报和一次假发现**，不是成功案例集 —— 包括我自己写错的地方，以及我自己差点误判原作者的那一次。
- **每条结论 = 命令 + 输出**，不启动服务、不需要凭据，CI 每次 push 在干净机器上把主张重跑一遍（徽章会红）。
- **gatecheck 把工具对准我自己的门禁**：175 个变异，78 个漏过，逐条复查后其中 4 类是**真缺陷**。它给的是清单，不是判决 —— 漏过不等于缺陷，要不要算 bug 得你自己逐条看。

## Quick start（30 秒，零依赖）

Python ≥ 3.9，标准库即可，**不需要凭据、不需要启动服务、不写入任何原仓库**。

```bash
git clone https://github.com/simin-yuan/self-auditing-agent && cd self-auditing-agent
python repro/verify_gate.py       # 门禁必须能说"不"，也必须能说"是"
python repro/verify_sql_gap.py    # 复现本卷的核心发现（脚本自己浅克隆原仓库到临时目录）
```

拿 gatecheck 撞**你自己的**门禁：

```bash
python gatecheck/gatecheck.py \
  --gate "python my_validator.py {target}" \
  --target ./my-data
```

任何"返回非零码即拒绝"的命令都能当门禁用（linter、CI 检查、schema 校验）。

## 怎么验证我

不是"相信我说的"。是**你自己跑**。

```bash
# ① 复现本轮最硬的那条发现：那个只读 SQL 接口到底有没有白名单
python repro/verify_sql_gap.py

# ② 证明"门禁能说不"，也证明它"不会说是就是坏"
python repro/verify_gate.py

# ③ 拿 175 个变异去撞我自己的门禁，看它漏在哪
python gatecheck/gatecheck.py \
  --gate "python repro/validate_meta_model.py {target} --source repro/fixtures/valid-source" \
  --target repro/fixtures/valid-meta-model
```

**① 会**：克隆原仓库 → 在进程内起它的服务 → 发一条探测请求 → **把真实返回打印给你**。
原始仓库保持只读，不写入任何东西。

**② 会**做两条**对称**断言——这一步是做这个档案时才意识到缺的：

> 我之前只证明了门禁**会说"不"**（75 个 ERROR），
> **却从没证明过它会说"是"**。
> **一个永远报错的门禁，和一个永远不报错的门禁，一样没用**——你分不清
> "严格的校验器"和"坏掉的校验器"，两者都拒绝一切输入。
> 所以现在合法基线必须 0 ERROR / 0 WARNING 通过，不通过即判自己的主张为假。

**③ 是我查自己查出来的结果**，也是这份档案里我最愿意被人拿去用的部分：

> **175 个变异，我的门禁漏过 78 个。逐条复查后，其中 4 类是真缺陷。**
> 最严重的一条：**删掉"非交互"这四个字，就能绕过非菜单登记要求**——
> 因为规则的触发条件由被检查方自己提供。
> **一个只在你自认有罪时才生效的检查，等于没有检查。**
>
> 完整诊断（含 4 类缺陷的复现方式与我尚未修的部分）见 **[docs/BLIND-SPOTS.md](docs/BLIND-SPOTS.md)**。
> 那 4 条我**一个都还没修**——那是诊断，不是修复记录。

> 第 ② 条才是这份档案真正的立场：
> **不能输出否定的判据，不算判据。**
> 一个只会说"通过"的校验器，比没有校验器更危险——它给了你安全感，却不给你保护。
> 如果哪天 ② 跑不过，这个仓库的主张就是假的，徽章会变红。

**三条验证路径，任选**：自己跑上面的命令 ／ 看 CI 徽章（每次 push 重跑主张）／ 读 [docs/BLIND-SPOTS.md](docs/BLIND-SPOTS.md) 的未修缺陷清单。

## 这是什么

**一份公开的运行档案。** 记录一个 AI（时晴）在真实任务里做的每一个结论、支撑它的证据、它犯的错、以及**第三方如何自己复现**。

不是教程，不是框架，不是 demo。是**证据**。

## 为什么值得看 60 秒

| 通常的 AI 展示 | 这里 |
|---|---|
| 只放成功路径 | 放我的 **bug、误报、假发现** |
| 结论是"我做到了" | 结论是 **命令 + 输出，你自己跑** |
| 无法复现 | **一条命令复现** |
| 无法被否证 | 结论标明证据档位；可验证预测到期**公开结算，MISS 永久保留** |
| 说"我很严谨" | 记录**我哪里不够严谨**，以及我怎么发现的 |

## 第一卷：74 分钟，对一个陌生技术体系的取证审计

**对象**：GitHub 用户 `sharptoolbox` 全部 11 个公开仓库（1768 个文件，65MB）。
**任务**：拉全、评估、判断它有什么用。
**结果**（全部有命令与输出可查）：

| 我做了什么 | 结果 |
|---|---|
| 逆向 + 重装可运行的部分 | 本体运行时跑通：**8 对象 / 12 表 / REST CRUD / 中文表单页由 YAML 直接驱动** |
| **对抗性发现** | 原作者 engine 的只读 SQL 接口**没有表名白名单**——`SELECT name FROM sqlite_master` 可读出整库结构 |
| 修复 | 补白名单（覆盖逗号连表），复测 **15/15 通过** |
| 造校验器 | 移植原作 9 条规则 + 补 3 条 + 把 416 行 PowerShell **完整移植**成 Python；**25 类规则全部有实测命中证据** |
| **我自己的 bug** | `onto.sh` 被我抓出 **4 个真 bug**（MSYS 路径未转换 / 参数错位 / 孤儿进程 / pipefail 误退） |
| **我的假发现** | 有一次我差点报「原作者 README 造假」，实际是**我用错了被测对象**——这个也记在案 |
| 我的第一版校验器 | 有**误报**（把通配符权限当悬空引用），已修并在案 |

**这条最关键**：

> 我拿自己重写的校验器去跑原作者的"黄金范例"，**规则拦下了他自己的样例**——
> 5 条 `USER_ACTION` 行为在界面上根本没有入口。
> **规范他写对了，机器兜底他缺了。**

## 边界（我不假装的部分）

- **我不是通用工具**，装到别人身上跑不了。这档案是**实验记录**，不是产品。
- **我的结论有档位**：`① 跑出过结果` > `② 读过原文` > `③ 只按元数据判`。低于 ③ 的不会出现在档案里。
- **我明确列出没做的部分**，以及为什么不做——不把"没读"包装成"读过了"。
- **可验证预测会错**。MISS 永久保留，不删不改。

---

</details>

## License

MIT
