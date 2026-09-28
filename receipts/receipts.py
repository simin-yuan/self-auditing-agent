#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""receipts.py —— 一份授权不是一次声明，是一张有范围、会到期、能撤销的收据。

第一性原理
----------
把「写下一条记录」和「授予一项权限」当成两件事、存进两个子系统，最贵的一类
事故就长这样：**一条在写入那一刻正确的记录，在动作发生那一刻已经失效，
而没有任何东西在动作处再问一次。**

收据把这两件事合成一个对象。一张收据带四样东西：

    provenance  谁签的、依据什么签的
    scope       它许可哪些动作
    expires_at  什么时候失效 —— **在动作处检查，不是记录里的日期**
    revocable   能不能被撤销（撤销后哪怕还没到期，也不再有效）

核心不变量
----------
    效力来自「被签发」，不来自「看起来还合适」。

一句话对照：把到期写成记录里的一个字段、在写入时判一次，那是**在保管一份
备忘录**；在每次使用动作处拿 `now` 再判一次，那才是**授权**。

零依赖（只用标准库）。这是被审计的机器，本身也必须可被第三方重跑。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

__all__ = [
    "make_receipt", "digest_of", "body_of", "is_intact",
    "check", "Decision", "Ledger", "Revocations", "utcnow", "parse_ts",
]

# 参与摘要的字段（顺序无关，序列化时排序）。digest 本身不在其中。
BODY_FIELDS = (
    "receipt_id", "subject", "scope", "provenance",
    "issued_by", "issued_at", "expires_at", "prev",
)

# 拒绝理由。分开命名，是为了让"为什么不行"可被断言，而不是只看到一个 False。
DENY_TAMPERED = "TAMPERED"            # 内容被改过，摘要对不上
DENY_REVOKED = "REVOKED"              # 已撤销（优先于到期判断）
DENY_OUT_OF_SCOPE = "OUT_OF_SCOPE"    # 这次动作不在它许可的范围里
DENY_NOT_YET_VALID = "NOT_YET_VALID"  # 还没到生效时间
DENY_EXPIRED = "EXPIRED_AT_USE"       # 到动作发生这一刻，它已经失效


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(ts) -> datetime:
    """解析 ISO 时间戳；无时区的按 UTC 处理，避免本地时区悄悄改变判定。"""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def body_of(receipt: dict) -> dict:
    """取出参与摘要的字段。这就是"这张收据到底写了什么"的规范形式。"""
    return {k: receipt.get(k) for k in BODY_FIELDS}


def digest_of(receipt: dict) -> str:
    canon = json.dumps(body_of(receipt), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def is_intact(receipt: dict) -> bool:
    return receipt.get("digest") == digest_of(receipt)


def make_receipt(subject: str, scope, provenance: str, ttl_seconds: float, *,
                 issued_at: datetime | None = None, issued_by: str = "",
                 prev: str = "", receipt_id: str | None = None) -> dict:
    """签发一张收据。

    scope 是动作名的列表，或 "*" 表示不限。ttl_seconds 从 issued_at 起算。
    provenance 是一句话：**凭什么签的**（"因为 X 测试通过" / "因为用户当场批准"）。
    没有 provenance 的收据 = 一张没有出处的许可条，不该存在。
    """
    if not provenance:
        raise ValueError("provenance 不可为空：一张没有出处的收据不是授权")
    issued_at = issued_at or utcnow()
    scopes = ["*"] if scope == "*" else sorted(scope)
    r = {
        "receipt_id": receipt_id or uuid.uuid4().hex[:16],
        "subject": subject,
        "scope": scopes,
        "provenance": provenance,
        "issued_by": issued_by,
        "issued_at": _iso(issued_at),
        "expires_at": _iso(issued_at + timedelta(seconds=float(ttl_seconds))),
        "prev": prev,
    }
    r["digest"] = digest_of(r)
    return r


class Decision:
    """判定结果。allowed 之外永远给出 reason —— 一个只给布尔值的门禁，没人能调试。"""

    __slots__ = ("allowed", "reason", "detail")

    def __init__(self, allowed: bool, reason: str = "OK", detail: str = ""):
        self.allowed = allowed
        self.reason = reason
        self.detail = detail

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"Decision(allowed={self.allowed}, reason={self.reason!r})"


def check(receipt: dict, action: str, *, now: datetime | None = None,
          revoked: "Revocations | set | frozenset | list | None" = None) -> Decision:
    """在**动作发生这一刻**判定这张收据还作不作数。

    顺序是刻意的：先问「它还是不是原来那张」（完整性），再问「它被撤销了吗」
    （撤销优先于到期 —— 撤销是主动收回，不该因为还没到期就被放过），
    再问范围，最后才拿 `now` 判时间。

    最后这步是整个模块存在的理由：**到期在这里判，不在签发处判。**
    """
    now = now or utcnow()

    if not isinstance(receipt, dict) or "receipt_id" not in receipt:
        return Decision(False, "MALFORMED", "不是一张收据")
    if not is_intact(receipt):
        return Decision(False, DENY_TAMPERED,
                        "内容与签发摘要不符 —— 这张收据签发后被改过")

    revoked_ids = revoked.ids() if isinstance(revoked, Revocations) else set(revoked or ())
    if receipt["receipt_id"] in revoked_ids:
        return Decision(False, DENY_REVOKED,
                        f"收据 {receipt['receipt_id']} 已被撤销")

    scope = receipt.get("scope") or []
    if "*" not in scope and action not in scope:
        return Decision(False, DENY_OUT_OF_SCOPE,
                        f"动作 {action!r} 不在许可范围 {scope} 内")

    t0, t1 = parse_ts(receipt["issued_at"]), parse_ts(receipt["expires_at"])
    if now < t0:
        return Decision(False, DENY_NOT_YET_VALID, f"生效时间 {receipt['issued_at']}")
    if now >= t1:
        age = (now - t1).total_seconds()
        return Decision(False, DENY_EXPIRED,
                        f"到动作发生这一刻已失效 {age:.0f}s（到期 {receipt['expires_at']}）")
    return Decision(True, "OK", f"剩余 {(t1 - now).total_seconds():.0f}s")


class Revocations:
    """撤销表。撤销按 receipt_id 生效，且**独立于收据本体**——
    如果撤销只能写在收据里，那撤销就变成了一次"改写历史"，而不是一次收回。"""

    def __init__(self):
        self._rows: list[dict] = []

    def revoke(self, receipt_id: str, *, at: datetime | None = None,
               reason: str = "", by: str = "") -> dict:
        row = {"receipt_id": receipt_id, "at": _iso(at or utcnow()),
               "reason": reason, "by": by}
        self._rows.append(row)
        return row

    def ids(self) -> set:
        return {r["receipt_id"] for r in self._rows}

    def __contains__(self, receipt_id: str) -> bool:
        return receipt_id in self.ids()

    def __len__(self) -> int:
        return len(self._rows)

    def rows(self) -> list:
        return list(self._rows)


class Ledger:
    """只追加的收据链。每张收据指向上一张的摘要（prev = 上一张的 digest）。

    链的价值不在"存了不少收据"，而在**顺序不可篡改**：抽走、调换、事后补一张，
    都会让链从某一点起对不上。verify_chain() 返回第一个断点，不是一句"不通过"。
    """

    def __init__(self):
        self._rows: list[dict] = []

    def issue(self, subject: str, scope, provenance: str, ttl_seconds: float, **kw) -> dict:
        prev = self._rows[-1]["digest"] if self._rows else ""
        r = make_receipt(subject, scope, provenance, ttl_seconds, prev=prev, **kw)
        self._rows.append(r)
        return r

    def verify_chain(self) -> tuple[bool, int, str]:
        """返回 (完整?, 断点下标, 原因)。下标记为 None-ish 时用 -1。"""
        prev = ""
        for i, r in enumerate(self._rows):
            if not is_intact(r):
                return False, i, "收据自身被改过（摘要不符）"
            if r.get("prev") != prev:
                return False, i, f"prev={r.get('prev')!r} 与上一张摘要 {prev!r} 不符"
            prev = r["digest"]
        return True, -1, ""

    def rows(self) -> list:
        return list(self._rows)

    def __len__(self) -> int:
        return len(self._rows)
