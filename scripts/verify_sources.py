#!/usr/bin/env python3
"""Validate the source registry and optionally probe official URLs."""

import argparse
import concurrent.futures
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

from source_lib import (
    AUTHORITIES,
    DEFAULT_SOURCES_PATH,
    OFFICIAL_SCOPES,
    REQUIRED_FIELDS,
    SOURCE_TYPES,
    STAGES,
    TEMPORALS,
)


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field}: 必须是 YYYY-MM-DD 或 null")
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field}: 非法日期 {value!r}")
        return None


def is_official_pku_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (host == "pku.edu.cn" or host.endswith(".pku.edu.cn"))


def validate_registry(data, as_of):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"], warnings
    if data.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    if "checked_at" not in data or data.get("checked_at") is None:
        errors.append("checked_at 为必填 YYYY-MM-DD")
        checked_at = None
    else:
        checked_at = parse_date(data.get("checked_at"), "checked_at", errors)
    if checked_at and checked_at > as_of:
        warnings.append(f"checked_at {checked_at} 晚于核验基准日 {as_of}")
    sources = data.get("sources")
    if not isinstance(sources, list):
        return errors + ["sources 必须是数组"], warnings
    if len(sources) < 25:
        errors.append(f"来源数不足：{len(sources)}，至少需要 25")

    ids = []
    urls = []
    scope_counts = Counter()
    stage_counts = Counter()
    temporal_counts = Counter()
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label}: 必须是对象")
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in source]
        if missing:
            errors.append(f"{label}: 缺少字段 {', '.join(missing)}")
            continue
        source_id = source["id"]
        if not isinstance(source_id, str) or not source_id or source_id.lower() != source_id:
            errors.append(f"{label}.id: 必须是非空小写字符串")
        else:
            ids.append(source_id)
        if not isinstance(source["title"], str) or not source["title"].strip():
            errors.append(f"{label}.title: 必须是非空字符串")
        url = source["url"]
        if not isinstance(url, str) or not is_official_pku_url(url):
            errors.append(f"{label}.url: 必须是 HTTPS 北京大学官方域名 URL")
        else:
            parsed = urllib.parse.urlsplit(url)
            canonical = urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))
            urls.append(canonical)

        for field, allowed, counter in (
            ("scope", OFFICIAL_SCOPES, scope_counts),
            ("stage", STAGES, stage_counts),
        ):
            values = source[field]
            if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
                errors.append(f"{label}.{field}: 必须是非空字符串数组")
            else:
                unknown = sorted(set(values) - set(allowed))
                if unknown:
                    errors.append(f"{label}.{field}: 未知值 {', '.join(unknown)}")
                counter.update(values)
        if source["authority"] not in AUTHORITIES:
            errors.append(f"{label}.authority: 未知值 {source['authority']!r}")
        if source["source_type"] not in SOURCE_TYPES:
            errors.append(f"{label}.source_type: 未知值 {source['source_type']!r}")
        temporal = source["temporal"]
        if temporal not in TEMPORALS:
            errors.append(f"{label}.temporal: 未知值 {temporal!r}")
        else:
            temporal_counts.update([temporal])
        published = parse_date(source["published_at"], f"{label}.published_at", errors)
        if published and published > as_of:
            errors.append(f"{label}.published_at: {published} 晚于基准日 {as_of}")
        valid_for = source["valid_for"]
        if not isinstance(valid_for, dict) or not isinstance(valid_for.get("cycles"), list) or "expires_at" not in valid_for:
            errors.append(f"{label}.valid_for: 需要 cycles 数组和 expires_at")
        else:
            expires = parse_date(valid_for["expires_at"], f"{label}.valid_for.expires_at", errors)
            if expires and expires < as_of and temporal != "historical":
                errors.append(f"{label}: 已于 {expires} 过期但 temporal 不是 historical")
        if not isinstance(source["summary"], str) or not source["summary"].strip():
            errors.append(f"{label}.summary: 必须是非空字符串")
        elif len(source["summary"]) > 300:
            warnings.append(f"{label}.summary: 超过 300 字符")
        keywords = source["keywords"]
        if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k for k in keywords):
            errors.append(f"{label}.keywords: 必须是非空字符串数组")
        claims = source["claims"]
        if not isinstance(claims, list) or not claims:
            errors.append(f"{label}.claims: 必须是非空数组")
        else:
            for claim_index, claim in enumerate(claims):
                claim_label = f"{label}.claims[{claim_index}]"
                if not isinstance(claim, dict) or not isinstance(claim.get("text"), str) or not claim.get("text"):
                    errors.append(f"{claim_label}: 需要非空 text")
                if not isinstance(claim, dict) or claim.get("temporal") not in TEMPORALS:
                    errors.append(f"{claim_label}.temporal: 非法或缺失")

    for name, values in (("id", ids), ("URL", urls)):
        duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
        if duplicates:
            errors.append(f"重复{name}: {', '.join(duplicates)}")
    for scope in OFFICIAL_SCOPES:
        if not scope_counts[scope]:
            errors.append(f"scope 无覆盖: {scope}")
    for stage in STAGES:
        if not stage_counts[stage]:
            errors.append(f"stage 无覆盖: {stage}")
    for temporal in TEMPORALS:
        if not temporal_counts[temporal]:
            errors.append(f"temporal 无覆盖: {temporal}")
    tongban_history = [
        source for source in sources
        if isinstance(source, dict)
        and "tongban" in source.get("scope", [])
        and source.get("temporal") == "historical"
    ]
    if not tongban_history:
        errors.append("缺少标为 historical 的通班官方历史来源")
    if not any(s.get("id") == "yuanpei-tongban-guide-2021" for s in tongban_history):
        errors.append("缺少 2021 通班简章历史锚点")
    return errors, warnings


def probe_url(source, timeout):
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "pku-ai-admissions-source-check/1.0", "Range": "bytes=0-1023"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            if not is_official_pku_url(final_url):
                return source["id"], False, f"重定向到非北大域名: {final_url}"
            return source["id"], 200 <= status < 400, f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        # Some PKU sites block automated probes with 403 while remaining valid
        # in a browser. Report it distinctly instead of claiming the URL is dead.
        return source["id"], False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return source["id"], False, f"{type(exc).__name__}: {exc}"


def build_parser():
    parser = argparse.ArgumentParser(description="核验 sources.json 的结构、范围和官方 URL。")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--as-of", default=dt.date.today().isoformat(), help="核验基准日 YYYY-MM-DD")
    parser.add_argument("--check-links", action="store_true", help="并发联网探测链接；默认不联网")
    parser.add_argument("--timeout", type=float, default=12.0, help="单链接超时秒数")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    try:
        as_of = dt.date.fromisoformat(args.as_of)
        data = json.loads(args.sources.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    errors, warnings = validate_registry(data, as_of)
    link_results = []
    if args.check_links and isinstance(data, dict) and isinstance(data.get("sources"), list):
        probe_candidates = [
            source for source in data["sources"]
            if isinstance(source, dict)
            and isinstance(source.get("id"), str)
            and isinstance(source.get("url"), str)
            and is_official_pku_url(source["url"])
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(probe_url, source, args.timeout) for source in probe_candidates]
            link_results = [future.result() for future in futures]
        for source_id, ok, detail in link_results:
            if not ok:
                message = f"链接探测 {source_id}: {detail}"
                if detail in ("HTTP 404", "HTTP 410"):
                    errors.append(message)
                else:
                    warnings.append(message)
    payload = {
        "ok": not errors,
        "source_count": len(data.get("sources", [])) if isinstance(data, dict) else 0,
        "errors": errors,
        "warnings": warnings,
        "links": [{"id": i, "ok": ok, "detail": detail} for i, ok, detail in link_results],
    }
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(f"sources: {payload['source_count']}  errors: {len(errors)}  warnings: {len(warnings)}")
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARN: {item}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
