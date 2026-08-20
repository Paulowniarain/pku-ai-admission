#!/usr/bin/env python3
"""Search local supplementary knowledge first, then official PKU sources."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from source_lib import SCOPES, STAGES, load_local_knowledge, load_sources, search


def build_parser():
    parser = argparse.ArgumentParser(
        description="先检索本地补充知识，再检索北大官方来源。"
    )
    parser.add_argument("query", help="中文查询，例如：2027智能学院博士招生指南")
    parser.add_argument(
        "--scope", action="append", choices=SCOPES,
        help="限定范围；可重复使用",
    )
    parser.add_argument(
        "--stage", action="append", choices=STAGES,
        help="限定培养阶段；可重复使用",
    )
    parser.add_argument("--limit", type=int, default=5, help="最多返回结果数（默认5）")
    parser.add_argument("--sources", type=Path, help="覆盖默认 sources.json 路径")
    parser.add_argument("--knowledge", type=Path, help="覆盖默认 local-knowledge.json 路径")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    return parser


def render_text(payload):
    print(f"查询：{payload['query']}")
    if payload["inferred_scopes"]:
        print("推断范围：" + ", ".join(payload["inferred_scopes"]))
    if payload["inferred_stages"]:
        print("推断阶段：" + ", ".join(payload["inferred_stages"]))
    if payload["guards"]:
        print("风险守卫：" + ", ".join(payload["guards"]))
    if payload["local_results"]:
        print("\n本地补充资料（优先读取；非官方）：")
        for number, item in enumerate(payload["local_results"], 1):
            date = item["as_of"] or "未标明确时间"
            locator = ", ".join(
                f"{key}=" + "/".join(str(value) for value in values)
                for key, values in item["locator"].items()
            )
            print(
                f"\nL{number}. {item['summary']}  "
                f"[score={item['score']}; {item['evidence_type']}; {item['claim_class']}; {date}]"
            )
            print(f"   来源：{item['source_filename']}（{locator}）")
            print(f"   限制：{item['usage_limit']}")
            if item["reasons"]:
                print("   命中：" + "；".join(item["reasons"]))
    if payload["results"]:
        print("\n北大官方来源（用于核验）：")
    for number, item in enumerate(payload["results"], 1):
        date = item["published_at"] or "持续更新/未标日期"
        print(f"\n{number}. {item['title']}  [score={item['score']}; {item['temporal']}; {date}]")
        print(f"   {item['url']}")
        print(f"   {item['summary']}")
        if item["reasons"]:
            print("   命中：" + "；".join(item["reasons"]))
    if not payload["local_results"] and not payload["results"]:
        print("未找到匹配资料。请缩短查询、改用项目全称或直接检查官方入口。")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        sources = None
        local_sources = None
        local_chunks = None
        if args.sources:
            _, sources = load_sources(args.sources)
        if args.knowledge:
            _, local_sources, local_chunks = load_local_knowledge(args.knowledge)
        payload = search(
            args.query,
            scopes=args.scope,
            stages=args.stage,
            limit=args.limit,
            sources=sources,
            local_sources=local_sources,
            local_chunks=local_chunks,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        render_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
