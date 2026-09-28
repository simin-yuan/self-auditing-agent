#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_permit.py —— 一个只检查「内容」的门，回答不了「授权还算不算数」。

这是 `receipts` 的**第一次真实应用**：把对外发布的批准做成一张带到期的收据，
并且在**发布动作发生的那一刻**检查它。

     python repro/verify_permit.py        # 退出码 0 = 全部主张成立

缺口长这样：一份稿子 21:00 被批准、TTL 30 分钟；22:00 某个循环把它捡起来发布。
私隐检查说 PASS —— 字是干净的。**文本没变，效力变了**，而门里没有任何东西
在发布那一刻再问一次。

主张（每一条都能失败）：
  Q1 内容门对一份干净产物放行 —— 所以它自己会把它发出去
  Q2 同一份产物，授权在发布时已过期 → 组合门拒绝，理由 EXPIRED_AT_USE
  Q3 新鲜授权 → 组合门放行（两道都过）
  Q4 授权绑定产物的哈希：签发后改了产物 → 拒绝 ARTIFACT_CHANGED
  Q5 未到期但被撤销 → 拒绝 REVOKED
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "receipts"))
from receipts import (  # noqa: E402
    Revocations, check, digest_of, make_receipt, utcnow,
)

PASS, FAIL = [], []
ARTIFACT = b"a clean outbound artifact: no private tokens here.\n"


def claim(cid: str, text: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(cid)
    print(f"  [{'PASS' if ok else '**FAIL**'}] {cid}  {text}")
    if detail:
        print(f"           {detail}")


def content_gate(blob: bytes):
    """这一层只回答「这份东西能不能出门」。它看不见时间，也看不见授权。"""
    banned = (b"secret", b"password", b"/home/", b"C:\\")
    hits = [w.decode() for w in banned if w.lower() in blob.lower()]
    return (not hits), (hits or ["CLEAN"])


def issue(blob: bytes, *, issued_ago_seconds: float = 0.0, ttl: float = 1800) -> dict:
    r = make_receipt("outbound:artifact", ["publish"], "reviewed and approved",
                     ttl, issued_at=utcnow() - timedelta(seconds=issued_ago_seconds),
                     issued_by="review")
    r["artifact_sha256"] = hashlib.sha256(blob).hexdigest()
    r["digest"] = digest_of(r)          # 摘要必须覆盖绑定字段，否则绑定是装饰品
    return r


def publish_gate(blob: bytes, permit: dict | None, *, revoked=None):
    """组合门：先内容，后授权。返回 (allowed, stage, reason)。"""
    ok, why = content_gate(blob)
    if not ok:
        return False, "content", f"BANNED_TOKENS{why}"
    if permit is None:
        return False, "permit", "NO_PERMIT"
    if permit.get("digest") != digest_of(permit):
        return False, "permit", "TAMPERED"
    if permit.get("artifact_sha256") != hashlib.sha256(blob).hexdigest():
        return False, "permit", "ARTIFACT_CHANGED"
    d = check(permit, "publish", revoked=(revoked or ()))
    return (d.allowed, "permit", d.reason if not d.allowed else "OK")


def main() -> int:
    print("=" * 74)
    print("verify_permit —— 内容干净 ≠ 授权还在")
    print("=" * 74)

    # Q1 —— 内容门自己会放行
    ok, why = content_gate(ARTIFACT)
    claim("Q1", "内容门对干净产物放行（所以它单独存在时，会把它发出去）",
          ok is True, f"content_gate → {why}")

    # Q2 —— 签发时有效，发布时已过期
    stale = issue(ARTIFACT, issued_ago_seconds=9000, ttl=1800)   # 2.5 小时前就到期
    allowed, stage, reason = publish_gate(ARTIFACT, stale)
    claim("Q2", "同一份产物 + 已过期的批准 → 组合门在 permit 这一级拒绝",
          (not allowed) and stage == "permit" and reason == "EXPIRED_AT_USE",
          f"签发 {stale['issued_at']} 到期 {stale['expires_at']} → {reason}")

    # Q3 —— 新鲜授权
    fresh = issue(ARTIFACT, issued_ago_seconds=5, ttl=1800)
    allowed3, stage3, reason3 = publish_gate(ARTIFACT, fresh)
    claim("Q3", "新鲜授权 → 放行（两道都过）",
          allowed3 and reason3 == "OK", f"{stage3} → {reason3}")

    # Q4 —— 绑定产物哈希
    edited = ARTIFACT + b"an extra line appended after approval\n"
    allowed4, stage4, reason4 = publish_gate(edited, fresh)
    claim("Q4", "签发后改了产物 → 拒绝 ARTIFACT_CHANGED（批准的是**那一次**的那一份）",
          (not allowed4) and reason4 == "ARTIFACT_CHANGED", f"{stage4} → {reason4}")

    # Q5 —— 撤销
    rev = Revocations()
    rev.revoke(fresh["receipt_id"], reason="withdrawn before expiry")
    allowed5, stage5, reason5 = publish_gate(ARTIFACT, fresh, revoked=rev)
    claim("Q5", "未到期但已撤销 → 拒绝 REVOKED（撤销优先于到期）",
          (not allowed5) and reason5 == "REVOKED", f"{stage5} → {reason5}")

    print("-" * 74)
    total = len(PASS) + len(FAIL)
    if FAIL:
        print(f"结论：{len(FAIL)}/{total} 条主张不成立。")
        print("      不成立：" + ", ".join(FAIL))
        return 1
    print(f"结论：{total}/{total} 条主张成立。")
    print("      Q1 与 Q2 合起来就是缺口：内容门说能发，授权门说此刻不作数。")
    print("      一个只检查内容的门，永远回答不了『这份批准现在还算不算数』。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
