#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_receipts.py —— 复现 receipts 的主张：有效期在**动作处**判，不在签发处判。

这份档案的规矩是：每条结论 = 一条命令 + 它的输出，每次推送在 CI 里重跑。
所以这里不写"我觉得它是对的"，这里造出**已知的坏**，要求每一件都被拒绝；
再造一个**干净的好**，要求它被放行。两侧都断言 —— 一个只会说不的判据，
和一个只会说是的判据，一样没用。

    python repro/verify_receipts.py      # 退出码 0 = 全部主张成立

主张清单（每一条都是一个可以失败的断言）：
  C1 签发时有效、使用时已过期的收据 → 拒绝，理由 EXPIRED_AT_USE
     （对照「签发时判一次」的天真实现：它会放行 —— 缺口就在这里）
  C2 撤销优先于到期：未到期但已撤销 → 拒绝，理由 REVOKED
  C3 越界动作 → 拒绝，理由 OUT_OF_SCOPE
  C4 签发后被改动过内容 → 拒绝，理由 TAMPERED
  C5 干净且未过期的收据 → 放行
  C6 撤销不改动收据本体：撤销后摘要不变（撤销是"收回"，不是"改写历史"）
  C7 收据链：链完整时通过；抽走一张后，断点必须在正确的位置被指出来
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "receipts"))

from receipts import (  # noqa: E402
    Ledger, Revocations, check, digest_of, make_receipt, utcnow,
    DENY_EXPIRED, DENY_OUT_OF_SCOPE, DENY_REVOKED, DENY_TAMPERED,
)

T0 = utcnow().replace(microsecond=0)
PASS, FAIL = [], []


def claim(cid: str, text: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(cid)
    print(f"  [{'PASS' if ok else '**FAIL**'}] {cid}  {text}")
    if detail:
        print(f"           {detail}")


def timestamp(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def receipt_expiry(r):
    return timestamp(r["expires_at"])


def naive_valid_at_issue(receipt, now_at_issue) -> bool:
    """天真的实现：只在**签发那一刻**判一次有效期，之后一路放行。

    很多系统的"到期"就是这样：写进去的是一条日期，读取时没人再拿当前时间比一次。
    """
    return (now_at_issue < receipt_expiry(receipt)
            and now_at_issue >= timestamp(receipt["issued_at"]))


def main() -> int:
    print("=" * 74)
    print("verify_receipts —— 有效期在动作处判，不在签发处判")
    print("=" * 74)

    # ---------------------------------------------------------------- C1
    # 签发时有效，使用时间落在到期之后 —— 这正是"写入那刻正确、动作那刻失效"。
    r = make_receipt("agent://shiqing", ["post.comment"], "ci 通过，签发 30 分钟",
                     ttl_seconds=1800, issued_at=T0, issued_by="gate")
    at_issue = T0 + timedelta(seconds=60)      # 签发后 1 分钟用：有效
    at_use = T0 + timedelta(seconds=3600)      # 1 小时后才用：已过期

    d_ok = check(r, "post.comment", now=at_issue)
    d_exp = check(r, "post.comment", now=at_use)
    naive = naive_valid_at_issue(r, at_issue)  # 天真实现只会看签发那一刻

    claim("C1a", "签发后即刻使用 → 放行", d_ok.allowed, repr(d_ok))
    claim("C1b", "签发时有效、使用时已过期 → 拒绝 EXPIRED_AT_USE",
          (not d_exp.allowed) and d_exp.reason == DENY_EXPIRED, repr(d_exp))
    claim("C1c", "对照：天真实现（只看签发那刻）会放行同一张收据",
          naive is True, "→ 这就是『记录里的日期』与『动作处的检查』之间的缺口")

    # ---------------------------------------------------------------- C2
    rev = Revocations()
    r2 = make_receipt("agent://shiqing", "*", "用户当场批准", ttl_seconds=86400, issued_at=T0)
    rev.revoke(r2["receipt_id"], at=T0 + timedelta(seconds=120), reason="用户撤回授权", by="human")
    d2 = check(r2, "post.comment", now=T0 + timedelta(seconds=300), revoked=rev)
    claim("C2", "未到期但已撤销 → 拒绝 REVOKED（撤销优先于到期）",
          (not d2.allowed) and d2.reason == DENY_REVOKED, repr(d2))

    # ---------------------------------------------------------------- C3
    r3 = make_receipt("agent://shiqing", ["read.fetch"], "只读授权", ttl_seconds=3600, issued_at=T0)
    d3 = check(r3, "post.comment", now=T0 + timedelta(seconds=60))
    claim("C3", "越界动作 → 拒绝 OUT_OF_SCOPE",
          (not d3.allowed) and d3.reason == DENY_OUT_OF_SCOPE, repr(d3))

    # ---------------------------------------------------------------- C4
    r4 = make_receipt("agent://shiqing", ["read.fetch"], "只读授权", ttl_seconds=3600, issued_at=T0)
    r4["scope"] = ["read.fetch", "post.comment"]   # 事后偷偷扩权，不改摘要
    d4 = check(r4, "post.comment", now=T0 + timedelta(seconds=60))
    claim("C4", "签发后被改动（偷偷扩权）→ 拒绝 TAMPERED",
          (not d4.allowed) and d4.reason == DENY_TAMPERED, repr(d4))

    # ---------------------------------------------------------------- C5
    r5 = make_receipt("agent://shiqing", ["post.comment"], "ci 通过", ttl_seconds=3600, issued_at=T0)
    d5 = check(r5, "post.comment", now=T0 + timedelta(seconds=60))
    claim("C5", "干净、未过期、在范围内 → 放行",
          d5.allowed and d5.reason == "OK", repr(d5))

    # ---------------------------------------------------------------- C6
    before = digest_of(r2)
    check(r2, "post.comment", now=T0 + timedelta(seconds=300), revoked=rev)
    after = digest_of(r2)
    claim("C6", "撤销不改动收据本体（收回 ≠ 改写历史）",
          before == after and len(rev) == 1, f"digest {before[:12]} 不变，撤销表 {len(rev)} 行")

    # ---------------------------------------------------------------- C7
    led = Ledger()
    led.issue("agent://shiqing", ["a"], "p1", 3600, issued_at=T0)
    led.issue("agent://shiqing", ["b"], "p2", 3600, issued_at=T0 + timedelta(seconds=1))
    led.issue("agent://shiqing", ["c"], "p3", 3600, issued_at=T0 + timedelta(seconds=2))
    ok, idx, why = led.verify_chain()
    claim("C7a", "完整链 → 通过", ok, f"链长 {len(led)}")

    rows = led.rows()
    rows.pop(1)                     # 抽走中间一张
    broken_led = Ledger()
    broken_led._rows = rows
    ok2, idx2, why2 = broken_led.verify_chain()
    claim("C7b", "抽走中间一张 → 断点被指在第 1 位（不是笼统一句『不通过』）",
          (not ok2) and idx2 == 1, f"idx={idx2} why={why2[:40]}")

    # ----------------------------------------------------------------
    print("-" * 74)
    total = len(PASS) + len(FAIL)
    if FAIL:
        print(f"结论：{len(FAIL)}/{total} 条主张不成立 —— 这套机制当前不可信。")
        print("      不成立：" + ", ".join(FAIL))
        return 1
    print(f"结论：{total}/{total} 条主张成立。")
    print("      两侧都断言过：该拒的拒（C1b–C4、C7b），该放的放（C1a、C5、C6、C7a）。")
    print("      C1c 是缺口本身：同一张收据，签发时判是有效的，使用时判是失效的 ——")
    print("      差别不在数据，在『谁在什么时候问了一次』。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
