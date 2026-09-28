#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_publish_gate.py —— 让 receipts 在一个真实动作点上真的拦下一次。

repro/verify_receipts.py 证明的是**模块**会在动作处拒绝；
这一份证明的是**动作本身没有发生**：拒绝不是一个返回值，是一个没被写出去的字节。

方法：把门装在一个真实的动作点（examples/publish_with_receipt.py）上，
用**真实时钟**跑几个场景，每个场景是一个独立进程。

  S1  没有收据                → DENY(NO_RECEIPT)，队列不存在
  S2  收据签发后过期           → DENY(EXPIRED_AT_USE)，队列 **零行**      ← 先红（时间戳落盘）
  S2d 同一张收据在*签发那一刻*判 → 有效（所以拦住它的是时间，不是这张票本身）
  S3  新签发的收据             → ALLOW，队列恰好 1 行                     ← 后绿
  S4  对照：同一张过期收据，在「只在签发处判一次」的天真实现下 → 会被放行

    python repro/verify_publish_gate.py                    # 退出码 0 = 全部主张成立
    python repro/verify_publish_gate.py --log out.jsonl    # 额外把红/绿时间戳落盘
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ACTION_SITE = ROOT / "examples" / "publish_with_receipt.py"

sys.path.insert(0, str(ROOT / "receipts"))
from receipts import check, make_receipt, utcnow  # noqa: E402

ACTION = "publish.post"
TTL_SHORT_S = 2.0     # 真实过期窗口：签发后 2 秒失效
WAIT_S = 2.6          # 真实等待：让墙上的钟真的走过到期点

PASS, FAIL = [], []


def claim(cid: str, text: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(cid)
    print(f"  [{'PASS' if ok else '**FAIL**'}] {cid}  {text}")
    if detail:
        print(f"           {detail}")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def gate_ts(line: str) -> str:
    """从门自己打的那一行里取时间戳 —— 那才是「变红」的真实时刻。"""
    if line.startswith("[") and "]" in line:
        return line[1:line.index("]")]
    return ""


def run_gate(receipt_path: Path, intent_path: Path, queue_path: Path):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.run(
        [sys.executable, str(ACTION_SITE),
         "--receipt", str(receipt_path),
         "--intent", str(intent_path),
         "--queue", str(queue_path),
         "--action", ACTION],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def naive_valid_at_issue(receipt: dict, now_at_issue: datetime) -> bool:
    """天真的实现：只在**签发那一刻**判一次有效期，之后一路放行。

    很多系统的「到期」就是这样：写进去的是一条日期，读取时没人再拿当前时间比一次。
    """
    e = datetime.fromisoformat(str(receipt["expires_at"]).replace("Z", "+00:00"))
    i = datetime.fromisoformat(str(receipt["issued_at"]).replace("Z", "+00:00"))
    return i <= now_at_issue < e


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", help="把红/绿的时间戳追加写成 jsonl（证据落盘）")
    args = ap.parse_args()

    print("=" * 74)
    print("verify_publish_gate —— 拒绝不是一个返回值，是一个没被写出去的字节")
    print("=" * 74)

    work = Path(tempfile.mkdtemp(prefix="publish_gate_"))
    intent = work / "intent.md"
    intent.write_text("draft body — 一份要对外发布的草稿\n", encoding="utf-8")
    queue = work / "queue.jsonl"
    evidence = []

    # ---------------------------------------------------------------- S1
    rc, out, err = run_gate(work / "no_such_receipt.json", intent, queue)
    claim("S1a", "没有收据 → 门拒绝（NO_RECEIPT），不是「跳过检查」",
          rc != 0 and "NO_RECEIPT" in out, out or err)
    claim("S1b", "被拒时队列文件不存在（动作没有发生）",
          not queue.exists(), f"queue_exists={queue.exists()}")

    # ---------------------------------------------------------------- 先红
    # 收据在**签发这一刻**是对的：签发后 2 秒内有效。让真实时钟走过到期点，
    # 再在同一个动作点做同一个动作 —— 这次它必须被拦下。
    issued = utcnow().replace(microsecond=0)
    r_exp = make_receipt("agent://shiqing", [ACTION],
                         "operator approved at issue time（示例）",
                         ttl_seconds=TTL_SHORT_S, issued_at=issued,
                         issued_by="examples/publish_with_receipt.py")
    r_path = work / "receipt_expired.json"
    r_path.write_text(json.dumps(r_exp, ensure_ascii=False), encoding="utf-8")

    at_issue = check(r_exp, ACTION, now=issued)          # 签发那一刻：有效
    time.sleep(WAIT_S)                                    # 真实的等待，不是 mock 的 now
    rc, out, err = run_gate(r_path, intent, queue)
    queue_bytes = len(queue.read_bytes()) if queue.exists() else 0

    print("-" * 74)
    print(f"  ① 红 — 同一张收据，{iso(issued)} 签发，{WAIT_S}s 后才使用：")
    claim("S2a", "过期收据在动作处被拒（退出码 != 0）", rc != 0, f"rc={rc}")
    claim("S2b", "拒绝理由是 EXPIRED_AT_USE（不是一个笼统的失败）",
          "EXPIRED_AT_USE" in out, out or err)
    claim("S2c", "队列仍是 0 字节 —— 动作本身没有发生",
          queue_bytes == 0, f"queue_bytes={queue_bytes}")
    claim("S2d", "同一张收据在*签发那一刻*判是有效的（拦住它的是时间，不是这张票本身）",
          at_issue.allowed and at_issue.reason == "OK", repr(at_issue))
    red_at = gate_ts(out) or iso(utcnow())
    print(f"      ★ 第一次变红的时间戳（门自己打的）：{red_at}")

    # ---------------------------------------------------------------- 后绿
    # 让红和绿在时间上真的分开 —— 否则两条证据落在同一秒里，
    # 「先红后绿」就只是一句断言，不是一条可以被别人复核的顺序。
    time.sleep(1.2)
    issued2 = utcnow().replace(microsecond=0)
    r_fresh = make_receipt("agent://shiqing", [ACTION],
                           "operator approved just now（示例）",
                           ttl_seconds=3600, issued_at=issued2,
                           issued_by="examples/publish_with_receipt.py")
    r2_path = work / "receipt_fresh.json"
    r2_path.write_text(json.dumps(r_fresh, ensure_ascii=False), encoding="utf-8")
    rc2, out2, err2 = run_gate(r2_path, intent, queue)
    lines = ([l for l in queue.read_text(encoding="utf-8").splitlines() if l.strip()]
             if queue.exists() else [])

    print("-" * 74)
    print("  ② 绿 — 新签发的收据，同一个动作点：")
    claim("S3a", "有效收据通过（退出码 0）", rc2 == 0, out2 or err2)
    claim("S3b", "队列恰好 1 行，且是这张收据写的",
          len(lines) == 1 and json.loads(lines[0])["receipt_id"] == r_fresh["receipt_id"],
          f"lines={len(lines)}")
    green_at = gate_ts(out2) or iso(utcnow())

    # ---------------------------------------------------------------- S4
    print("-" * 74)
    print("  ③ 对照 — 同一张过期收据，换一个天真的实现：")
    naive = naive_valid_at_issue(r_exp, issued)
    strict = check(r_exp, ACTION, now=datetime.fromisoformat(red_at))
    claim("S4", "「只在签发处判一次」的实现会放行同一张收据 → 缺口就在这里",
          naive is True and not strict.allowed,
          f"naive_at_issue={naive}  checked_at_use={strict.reason}")

    # ---------------------------------------------------------------- 落盘
    evidence.append({"phase": "red", "at": red_at, "receipt_id": r_exp["receipt_id"],
                     "gate_reason": "EXPIRED_AT_USE", "queue_bytes": queue_bytes})
    evidence.append({"phase": "green", "at": green_at, "receipt_id": r_fresh["receipt_id"],
                     "gate_reason": "OK", "queue_lines": len(lines)})
    if args.log:
        p = Path(args.log)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            for row in evidence:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  证据已落盘：{p}")

    print("-" * 74)
    total = len(PASS) + len(FAIL)
    if FAIL:
        print(f"结论：{len(FAIL)}/{total} 条主张不成立 —— {', '.join(FAIL)}")
        return 1
    print(f"结论：{total}/{total} 条主张成立。")
    print("      先红后绿：过期授权在动作处被拦（队列零字节），新授权通过（队列 1 行）。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
