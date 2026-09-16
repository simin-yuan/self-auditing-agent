#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现本轮最硬的一条发现：原作者的只读 SQL 接口【没有表名白名单】。

它拦得住写操作，拦不住"读取任意表"——`SELECT name FROM sqlite_master`
可以读出整个库的结构。

本脚本不启动任何服务、不装任何依赖、不写入原仓库：直接把原仓库的
`engine/query.py` 作为模块加载，用一个临时 sqlite 库调用它，把真实返回打印出来。

用法：
    python repro/verify_sql_gap.py                # 自动浅克隆原仓库到临时目录
    python repro/verify_sql_gap.py --repo <路径>  # 用已有的本地克隆
退出码：
    0 = 复现成功（发现成立：任意表读取被放行）
    1 = 无法复现（发现可能已被上游修复）
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

REPO_URL = "https://github.com/sharptoolbox/WorkBuddy-AppBuilderSkill.git"
ENGINE_QUERY = os.path.join("engine", "query.py")

PROBE = "SELECT name FROM sqlite_master"          # 读取整个库的结构
WRITE_PROBE = "DELETE FROM demo"                   # 对照组：写操作


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def make_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE demo (id TEXT PRIMARY KEY, secret TEXT)")
    conn.execute("CREATE TABLE hidden_audit_log (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO demo VALUES ('1', 'should-not-be-readable-by-design')")
    conn.commit()
    return conn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="已有的本地克隆路径（不给则自动浅克隆）")
    args = ap.parse_args()

    tmp = None
    repo = args.repo
    if not repo:
        tmp = tempfile.mkdtemp(prefix="sqlgap_")
        repo = os.path.join(tmp, "WorkBuddy-AppBuilderSkill")
        print(f"[1/4] 浅克隆原仓库 → {repo}")
        r = subprocess.run(["git", "clone", "--depth", "1", "-q", REPO_URL, repo],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      克隆失败：", r.stderr.strip()[:200])
            print("      （网络不可用时，可用 --repo 指向已有克隆）")
            return 1
    else:
        print(f"[1/4] 使用本地克隆 → {repo}")

    try:
        qpath = os.path.join(repo, ENGINE_QUERY)
        if not os.path.exists(qpath):
            print(f"      找不到 {qpath}")
            return 1
        print(f"[2/4] 加载原实现 {ENGINE_QUERY}（不启动服务、不改动仓库）")
        # query.py 里有 `from db import dict_label` 这类同目录导入，需要把 engine 目录入 sys.path
        sys.path.insert(0, os.path.dirname(qpath))
        q = load_module(qpath, "orig_engine_query")

        dbdir = tempfile.mkdtemp(prefix="sqlgap_db_")
        conn = make_db(os.path.join(dbdir, "probe.db"))
        print("      已建临时库，含 2 张表：demo、hidden_audit_log")

        print("[3/4] 对照组：写操作应被拦")
        try:
            q.run_readonly_sql(conn, WRITE_PROBE)
            print("      ❌ 写操作竟然被放行")
            write_blocked = False
        except ValueError as e:
            print(f"      ✅ 写操作被拦：{e}")
            write_blocked = True

        print("[4/4] 关键探针：读取任意表")
        try:
            cols, rows = q.run_readonly_sql(conn, PROBE)
            print(f"      ⚠️  被【放行】。返回 {len(rows)} 张表：")
            for r_ in rows:
                print(f"          - {dict(r_)}")
            leaked = True
        except ValueError as e:
            print(f"      ✅ 被拦：{e}")
            leaked = False

        print()
        print("=" * 62)
        if leaked and write_blocked:
            print("发现成立：该实现拦得住写，拦不住【任意表读取】——")
            print("只读 SQL 接口缺少表名白名单，模型可据此枚举整库结构。")
            print("（修复建议：白名单由本体模型推出，并对 from/join/逗号连表统一校验）")
            code = 0
        elif not leaked:
            print("无法复现：该实现已经拦住了任意表读取（可能已被上游修复）。")
            print("若如此，本条发现应标记为『已失效』。")
            code = 1
        else:
            print("结果异常：写操作未被拦住，与本发现的描述不符。")
            code = 1
        print("=" * 62)

        conn.close()
        shutil.rmtree(dbdir, ignore_errors=True)
        return code
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
