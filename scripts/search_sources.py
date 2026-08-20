#!/usr/bin/env python3
"""Search the curated official PKU admissions source registry."""

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from source_lib import SCOPES, STAGES, load_sources, search


def build_parser():
    parser = argparse.ArgumentParser(
        description="检索北大招生、元培、通班与智能学科官方来源。"
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
    if not payload["results"]:
        print("未找到匹配来源。请缩短查询或直接检查官方入口。")
        return
    for number, item in enumerate(payload["results"], 1):
        date = item["published_at"] or "持续更新/未标日期"
        print(f"\n{number}. {item['title']}  [score={item['score']}; {item['temporal']}; {date}]")
        print(f"   {item['url']}")
        print(f"   {item['summary']}")
        if item["reasons"]:
            print("   命中：" + "；".join(item["reasons"]))


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        sources = None
        if args.sources:
            _, sources = load_sources(args.sources)
        payload = search(
            args.query,
            scopes=args.scope,
            stages=args.stage,
            limit=args.limit,
            sources=sources,
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
