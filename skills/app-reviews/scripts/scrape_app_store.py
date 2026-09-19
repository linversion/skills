#!/usr/bin/env python3
"""抓取 App Store (iOS) 应用评论并按国家导出 CSV（与安卓版同格式）。

用法:
    python3 <skill目录>/scripts/scrape_app_store.py <App数字id或bundleId> [每国条数上限] [--tier t2]

数据源为苹果官方 iTunes RSS 评论接口:
    https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={appid}/sortby=mostrecent/json

特性与限制:
- 各国商店独立返回（评论按 storefront 真实隔离, 无安卓那种同语言池现象）
- 每国最多 10 页 × 50 条 = 500 条
- 无开发者回复、无点赞数; 评论标题与正文合并写入 content
- bundleId 会先经 lookup 解析成数字 id
"""

import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from scrape_play_reviews import markets_for_tier  # 复用 T1/T2/T3 市场层级

PAGE_SLEEP = 0.5
MAX_PAGES = 10

CSV_COLS = [
    "reviewId", "countries", "primary_country", "score", "content",
    "reviewCreatedVersion", "at", "thumbsUpCount", "userName",
    "replyContent", "repliedAt",
]


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve_app_id(app_ref: str) -> str:
    """bundleId -> 数字 trackId; 数字 id 原样返回。"""
    if app_ref.isdigit():
        return app_ref
    d = get_json("https://itunes.apple.com/lookup?bundleId=" + app_ref)
    results = d.get("results") or []
    if not results:
        raise SystemExit(f"无法解析 bundleId: {app_ref} (lookup 无结果)")
    return str(results[0]["trackId"])


def lookup_title(app_ref: str) -> str:
    """按 id 或 bundleId 取应用展示名, 失败退回原值。"""
    key = "id" if app_ref.isdigit() else "bundleId"
    try:
        d = get_json(f"https://itunes.apple.com/lookup?{key}={app_ref}")
        results = d.get("results") or []
        return str(results[0]["trackName"]) if results else app_ref
    except Exception:
        return app_ref


def _normalize(entry: dict) -> dict:
    title = (entry.get("title") or {}).get("label", "").strip()
    content = (entry.get("content") or {}).get("label", "").strip()
    body = (title + "\n" + content).strip() if title and title != content else (content or title)
    updated = (entry.get("updated") or {}).get("label", "")
    at = ""
    if updated:
        try:
            at = (
                datetime.fromisoformat(updated)
                .astimezone(timezone.utc)
                .strftime("%Y-%m-%d %H:%M:%S")
            )
        except ValueError:
            at = updated
    try:
        score = int((entry.get("im:rating") or {}).get("label", 0) or 0)
    except ValueError:
        score = 0
    return {
        "reviewId": (entry.get("id") or {}).get("label", ""),
        "score": score,
        "content": body,
        "reviewCreatedVersion": (entry.get("im:version") or {}).get("label", ""),
        "at": at,
        "thumbsUpCount": 0,
        "userName": ((entry.get("author") or {}).get("name") or {}).get("label", ""),
        "replyContent": "",
        "repliedAt": "",
    }


def ios_reviews(app_ref: str, country: str, max_count: int) -> list:
    """抓一国 storefront 的评论, 翻页至 MAX_PAGES 或取满 max_count。"""
    out = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews/"
            f"page={page}/id={app_ref}/sortby=mostrecent/json"
        )
        d = get_json(url)
        entries = d.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):  # 单条时 JSON 是对象不是数组
            entries = [entries]
        if not entries:
            break
        out.extend(_normalize(e) for e in entries)
        if len(out) >= max_count or len(entries) < 50:
            break
        time.sleep(PAGE_SLEEP)
    return out[:max_count]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    app_ref = sys.argv[1].strip()
    per_country = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "t1"
    markets = markets_for_tier(tier)
    app_id = resolve_app_id(app_ref)

    merged: dict[str, dict] = {}
    for country in markets:
        try:
            result = ios_reviews(app_id, country, per_country)
        except Exception as e:
            print(f"[{country}] 失败: {e}")
            continue
        new = 0
        for r in result:
            rid = r["reviewId"]
            if rid in merged:
                merged[rid]["countries"].append(country)
            else:
                merged[rid] = {"review": r, "countries": [country]}
                new += 1
        print(f"[{country}] {len(result)} 条 (新增 {new}), 累计 {len(merged)}")
        time.sleep(1.0)

    out_path = Path(__file__).resolve().parent.parent / "assets" / "csv" / f"{app_id}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for rid, entry in merged.items():
            r = entry["review"]
            countries = list(dict.fromkeys(entry["countries"]))
            w.writerow([
                rid, "|".join(countries), countries[0], r["score"], r["content"],
                r["reviewCreatedVersion"], r["at"], r["thumbsUpCount"],
                r["userName"], r["replyContent"], r["repliedAt"],
            ])
    print(f"已导出 {len(merged)} 条 -> {out_path}  ({lookup_title(app_id)})")


if __name__ == "__main__":
    main()
