#!/usr/bin/env python3
"""把 scrape_play_reviews.py 导出的评论 CSV 转成看板页面可用的 data.js。

用法:
    python3 <skill目录>/scripts/csv_to_reviews_js.py <输入.csv> <输出data.js> [--app <包名>]

示例:
    python3 <skill目录>/scripts/csv_to_reviews_js.py \
        <skill目录>/assets/csv/<app>.csv \
        <skill目录>/assets/dashboard/data.js --app <包名>
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    app_id = ""
    if "--app" in sys.argv:
        app_id = sys.argv[sys.argv.index("--app") + 1]

    with src.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    reviews = []
    for r in rows:
        reviews.append(
            {
                "reviewId": r["reviewId"],
                "countries": r["countries"],
                "primary_country": r["primary_country"],
                "score": int(r["score"] or 0),
                "content": r["content"],
                "reviewCreatedVersion": r["reviewCreatedVersion"],
                "at": r["at"],
                "thumbsUpCount": int(r["thumbsUpCount"] or 0),
                "userName": r["userName"],
                "replyContent": r["replyContent"],
                "repliedAt": r["repliedAt"],
            }
        )

    payload = {
        "app_id": app_id or src.stem,
        "source_csv": str(src),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "reviews": reviews,
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        "// 由 scripts/csv_to_reviews_js.py 生成 — 请勿手改\n"
        f"window.REVIEWS_DATA = {json.dumps(payload, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    print(f"已写入 {len(reviews)} 条评论 -> {dst}")


if __name__ == "__main__":
    main()
