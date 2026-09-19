#!/usr/bin/env python3
"""按国家抓取 Google Play 应用评论并去重导出 CSV。

用法:
    python3 scripts/scrape_play_reviews.py <app_id> [每国抓取条数] [输出CSV路径]

示例:
    python3 scripts/scrape_play_reviews.py gmikhail.colorpicker 500 artifacts/play_reviews/gmikhail_colorpicker.csv

说明:
- 使用 google-play-scraper (JoMingyu) 库, 底层为 Play Store 内部 batchexecute 接口
- country/lang 成对传入 (对应 gl/hl), sort=NEWEST 地区差异最明显
- 同一语言的英语区 (us/gb/ca/au) 返回结果高度重叠, 按 reviewId 去重并记录出现国家
"""

import csv
import sys
import time
from collections import Counter
from pathlib import Path

from google_play_scraper import reviews, Sort

# T1 国家 -> 对应语言 (country=gl, lang=hl)
T1_MARKETS = {
    "us": "en",
    "gb": "en",
    "ca": "en",
    "au": "en",
    "de": "de",
    "fr": "fr",
    "jp": "ja",
    "kr": "ko",
}

# T2: 其他发达市场 (西欧/北欧/亚太发达/海湾)
T2_MARKETS = {
    "nl": "nl",
    "be": "nl",
    "at": "de",
    "ch": "de",
    "ie": "en",
    "it": "it",
    "es": "es",
    "pt": "pt",
    "pl": "pl",
    "se": "sv",
    "no": "no",
    "dk": "da",
    "fi": "fi",
    "nz": "en",
    "sg": "en",
    "tw": "zh-tw",
    "hk": "zh-tw",
    "ae": "en",
}

# T3: 新兴市场
T3_MARKETS = {
    "br": "pt",
    "mx": "es",
    "ar": "es",
    "cl": "es",
    "co": "es",
    "in": "en",
    "id": "id",
    "my": "en",
    "ph": "en",
    "th": "th",
    "vn": "vi",
    "tr": "tr",
    "ru": "ru",
    "za": "en",
    "sa": "ar",
    "eg": "en",
    "ng": "en",
}

# tier 为累积语义: t2 = T1+T2, t3/all = T1+T2+T3 全部
MARKET_TIERS = {
    "t1": T1_MARKETS,
    "t2": {**T1_MARKETS, **T2_MARKETS},
    "t3": {**T1_MARKETS, **T2_MARKETS, **T3_MARKETS},
    "all": {**T1_MARKETS, **T2_MARKETS, **T3_MARKETS},
}


def markets_for_tier(tier: str) -> dict:
    return MARKET_TIERS.get((tier or "t1").lower(), T1_MARKETS)


REQUEST_SLEEP_SECONDS = 2.0  # 每个国家之间的间隔, 避免被限流


def scrape_app(app_id: str, per_country: int, out_path: Path, markets: dict | None = None) -> None:
    markets = markets if markets is not None else T1_MARKETS
    # reviewId -> {"review": dict, "countries": [..]}
    merged: dict[str, dict] = {}
    per_country_counts: dict[str, int] = {}

    for country, lang in markets.items():
        try:
            result, _ = reviews(
                app_id,
                lang=lang,
                country=country,
                sort=Sort.NEWEST,
                count=per_country,
            )
        except Exception as e:
            print(f"[{country}] 抓取失败: {e}")
            continue

        new_count = 0
        for r in result:
            rid = r["reviewId"]
            if rid in merged:
                merged[rid]["countries"].append(country)
            else:
                merged[rid] = {"review": r, "countries": [country]}
                new_count += 1
        per_country_counts[country] = len(result)
        print(
            f"[{country}] 返回 {len(result)} 条, 其中 {new_count} 条是首次出现, 累计 {len(merged)} 条"
        )
        time.sleep(REQUEST_SLEEP_SECONDS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "reviewId",
                "countries",
                "primary_country",
                "score",
                "content",
                "reviewCreatedVersion",
                "at",
                "thumbsUpCount",
                "userName",
                "replyContent",
                "repliedAt",
            ]
        )
        for rid, entry in merged.items():
            r = entry["review"]
            # 按首次出现顺序去重, primary_country 才能反映实际抓取来源
            countries = list(dict.fromkeys(entry["countries"]))
            writer.writerow(
                [
                    rid,
                    "|".join(countries),
                    countries[0],
                    r.get("score"),
                    r.get("content", ""),
                    r.get("reviewCreatedVersion", ""),
                    r.get("at", ""),
                    r.get("thumbsUpCount", 0),
                    r.get("userName", ""),
                    r.get("replyContent", ""),
                    r.get("repliedAt", ""),
                ]
            )

    print(f"\n已导出 {len(merged)} 条去重评论 -> {out_path}")
    print("\n=== 各国返回条数 ===")
    for c, n in per_country_counts.items():
        print(f"  {c}: {n}")
    print("\n=== 去重后评分分布 ===")
    for score, n in sorted(Counter(e["review"]["score"] for e in merged.values()).items()):
        print(f"  {score} 星: {n}")
    only_in = Counter(e["countries"][0] for e in merged.values())
    print("\n=== 首次出现国家分布(近似各国独有量) ===")
    for c, n in sorted(only_in.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    app_id = sys.argv[1]
    per_country = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    default_out = Path(__file__).resolve().parent.parent / "assets" / "csv" / f"{app_id.replace('.', '_')}.csv"
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else default_out
    tier = sys.argv[sys.argv.index("--tier") + 1] if "--tier" in sys.argv else "t1"
    scrape_app(app_id, per_country, out_path, markets_for_tier(tier))
