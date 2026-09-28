#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_with_receipt.py —— 一个真实的对外发布动作点，门上只挂一张收据。

这是**动作点**，不是库。它演示 receipts 最难的那一步：
**检查发生在动作发生的那一刻，不是在授权被写下的那一刻。**

    python examples/publish_with_receipt.py \
        --receipt r.json --intent draft.md --queue queue.jsonl

退出码：
    0  收据在动作这一刻仍然有效 → 意图进入队列
    1  收据不存在 / 已被拒      → 队列**一个字节都不动**

第二条才是重点。一个「先写一半、再报错」的门不是门 ——
拒绝的强度不在于它返回了什么，在于**什么都没有发生**。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "receipts"))

from receipts import check, utcnow  # noqa: E402

DEFAULT_ACTION = "publish.post"


def main() -> int:
    ap = argparse.ArgumentParser(description="A publish action whose only door is a receipt.")
    ap.add_argument("--receipt", required=True, help="收据 JSON（一张授权）")
    ap.add_argument("--intent", required=True, help="要发布的正文")
    ap.add_argument("--queue", required=True, help="通过后写入的草稿队列（jsonl）")
    ap.add_argument("--action", default=DEFAULT_ACTION,
                    help=f"动作名，默认 {DEFAULT_ACTION}")
    args = ap.parse_args()

    now = utcnow()
    ts = now.isoformat(timespec="seconds")

    # 读不到收据 = 没有授权，不是「跳过检查」。
    try:
        receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[{ts}] GATE DENY action={args.action} reason=NO_RECEIPT "
              f"detail={type(exc).__name__}: {exc}")
        return 1

    d = check(receipt, args.action, now=now)          # ← 检查在这一刻发生
    rid = receipt.get("receipt_id", "?") if isinstance(receipt, dict) else "?"

    if not d.allowed:
        print(f"[{ts}] GATE DENY action={args.action} receipt={rid} "
              f"reason={d.reason} detail={d.detail}")
        return 1

    intent = Path(args.intent).read_text(encoding="utf-8")
    with Path(args.queue).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"queued_at": ts, "action": args.action,
                            "receipt_id": rid, "intent": intent},
                           ensure_ascii=False) + "\n")
    print(f"[{ts}] GATE ALLOW action={args.action} receipt={rid} "
          f"reason={d.reason} detail={d.detail} → queued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
