# receipts

**A permission is not a statement. It is a receipt with a scope, an expiry, and a revocation.**

The failure this exists for is not a wrong belief. It is a correct record
that stopped being true between the moment it was written and the moment it
was used — with nothing at the point of use asking the question a second time.

## The one rule

> **Validity comes from being *issued*, not from *looking still appropriate*.**

Store an expiry as a field and check it once at write time, and you are keeping
a memo. Re-check it against `now` at every point of use, and you have an
authorization. The difference is not in the data. It is in **who asks, and when.**

## The four fields

| field | what it answers |
|---|---|
| `provenance` | who signed it, and *on what basis* — a receipt with no provenance is a permission slip with no author |
| `scope` | which actions it permits (`["post.comment"]`, or `"*"`) |
| `expires_at` | when it stops being valid — **checked at the point of use** |
| revocation | a receipt can be withdrawn before it expires; withdrawal lives *outside* the receipt |

Revocation is deliberately kept out of the receipt body: if the only way to
revoke is to edit the receipt, that is not a withdrawal, it is rewriting history.

## What it refuses, and why each refusal is named

`check(receipt, action, now=...)` returns a decision with a reason:

| reason | when |
|---|---|
| `TAMPERED` | the body no longer matches the digest it was signed with |
| `REVOKED` | withdrawn (checked **before** expiry — withdrawing beats merely aging out) |
| `OUT_OF_SCOPE` | this action is not among the permitted ones |
| `NOT_YET_VALID` | used before it becomes effective |
| `EXPIRED_AT_USE` | it was valid when issued, and is not valid now |

A gate that returns only `True`/`False` cannot be debugged. Every refusal names itself.

## The chain

`Ledger` is an append-only chain: each receipt carries the previous receipt's
digest in `prev`. Its value is not that it stores many receipts — it is that the
**order cannot be edited**: pull one out, swap two, or append one after the fact,
and `verify_chain()` names the first index where the chain stops adding up.
It returns a position, not a mood.

## What this does NOT do

It does not decide *who* may issue receipts, and it does not sign with a private
key. `issued_by` is a label; tamper-evidence comes from the digest, not from
cryptographic unforgeability. If you need an adversary who can rewrite the whole
ledger, you need signatures on top — this is the layer above that, where the
question is *"is this still in force right now"*, not *"was this really signed."*

## Verify it

```bash
python repro/verify_receipts.py       # 模块层：check() 在动作处拒绝
python repro/verify_publish_gate.py   # 动作层：拒绝不是一个返回值，是一个没被写出去的字节
```

The first is the module answering a question. The second is the **action not
happening**: the gate sits at a real publish site (`examples/publish_with_receipt.py`),
a receipt is issued, real time is allowed to pass its expiry, and the gate refuses —
queue still zero bytes. A fresh receipt then goes through. Red first, green after,
both timestamps written down. One claim is the control: the *same* expired receipt
is valid at issue time and is let through by a check-at-issue implementation.

Ten claims in the first run, both directions asserted: the ones that must be
refused are refused, and the clean one is allowed. The run includes the exact gap
this module closes — the same receipt that a *check-at-issue* implementation lets
through:

```
[PASS] C1b  签发时有效、使用时已过期 → 拒绝 EXPIRED_AT_USE
[PASS] C1c  对照：天真实现（只看签发那刻）会放行同一张收据
```

Zero dependencies, standard library only, Python ≥ 3.9.

---

## 中文

**一份授权不是一次声明，是一张有范围、会到期、能撤销的收据。**

它存在的理由是这一类事故：**一条在写入那一刻正确的记录，在动作发生那一刻已经
失效，而没有任何东西在动作处再问一次。**

一条不变量：**效力来自「被签发」，不来自「看起来还合适」。**

把到期写成记录里的一个字段、在写入时判一次，那是保管一份备忘录；在每次使用动作
处拿 `now` 再判一次，那才是授权。差别不在数据，**在谁、在什么时候问了一次。**

四样东西：来源（凭什么签的）、范围（许可哪些动作）、到期（在动作处检查）、
可撤销（撤销独立于收据本体 —— 只能靠改写收据来撤销，那不是收回，是改写历史）。

拒绝理由分开命名：`TAMPERED` / `REVOKED` / `OUT_OF_SCOPE` / `NOT_YET_VALID` /
`EXPIRED_AT_USE`。只返回 True/False 的门禁没法调试。

链（`Ledger`）的价值不在存得多，在**顺序不可篡改**：抽走、调换、事后补一张，
`verify_chain()` 指出第一个对不上的位置 —— 给位置，不给情绪。

跑一遍：`python repro/verify_receipts.py`（10 条主张，两个方向都断言）。
