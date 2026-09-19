#!/usr/bin/env python3
"""评论看板专用本地服务器: 静态托管 assets/ + /api/scrape 实时抓取接口。

用法:
    python3 <skill目录>/scripts/serve_reviews.py [端口, 默认 4318]

Skill 完全自包含: 看板与数据都在 <skill>/assets/ 下, 与任何仓库解耦,
从任意目录启动均可。页面上的「拉取最新」按钮会请求 /api/scrape?app=<包名>,
本服务器逐国抓取并以 NDJSON 流式返回进度和最终数据, 同时自动落盘
CSV 到 assets/csv/ 并刷新看板的 apps/ 与 data.js。
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATE_DIR = ASSETS_DIR / "dashboard"
CSV_DIR = ASSETS_DIR / "csv"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google_play_scraper import Sort, app as app_meta, reviews  # noqa: E402
from scrape_play_reviews import (  # noqa: E402
    MARKET_TIERS,
    REQUEST_SLEEP_SECONDS,
    T1_MARKETS,
    markets_for_tier,
)
from scrape_app_store import ios_reviews, lookup_title, resolve_app_id  # noqa: E402

APPS_DIR = TEMPLATE_DIR / "apps"


def fetch_title(app_id: str, platform: str) -> str:
    """拉应用展示名: Android 走 Play 商店, iOS 走 itunes lookup; 失败退回标识。"""
    if platform == "ios":
        return lookup_title(app_id)
    try:
        meta = app_meta(app_id)
        return str(meta.get("title") or app_id)
    except Exception:
        return app_id


def scrape_to_payload(app_id: str, per_country: int, markets: dict, emit, platform: str = "android") -> dict:
    if platform == "ios":
        app_id = resolve_app_id(app_id)  # bundleId -> 数字 id; 失败则整体 fatal
    merged: dict[str, dict] = {}
    errors = []
    for country, lang in markets.items():
        try:
            if platform == "ios":
                result = ios_reviews(app_id, country, per_country)
            else:
                result, _ = reviews(
                    app_id, lang=lang, country=country, sort=Sort.NEWEST, count=per_country
                )
        except Exception as e:  # 单国失败不中断整体
            errors.append(f"{country}: {e}")
            emit({"type": "progress", "country": country, "error": str(e)})
            continue
        new = 0
        for r in result:
            rid = r["reviewId"]
            if rid in merged:
                merged[rid]["countries"].append(country)
            else:
                merged[rid] = {"review": r, "countries": [country]}
                new += 1
        emit(
            {
                "type": "progress",
                "country": country,
                "got": len(result),
                "new": new,
                "total": len(merged),
            }
        )
        time.sleep(1.0 if platform == "ios" else REQUEST_SLEEP_SECONDS)

    # 全部国家都失败 => 网络层问题, 判整体失败而非落盘 0 条
    if not merged and errors:
        host = "itunes.apple.com" if platform == "ios" else "play.google.com"
        raise RuntimeError(
            f"全部 {len(markets)} 个国家抓取失败, 疑似网络问题(需可访问 {host}, "
            f"国内网络通常需要代理)。首个错误: {errors[0][:150]}"
        )

    out = []
    for entry in merged.values():
        r = entry["review"]
        countries = list(dict.fromkeys(entry["countries"]))

        def as_str(v):
            return "" if v is None else str(v)

        out.append(
            {
                "reviewId": r["reviewId"],
                "countries": "|".join(countries),
                "primary_country": countries[0],
                "score": r.get("score", 0),
                "content": as_str(r.get("content", "")),
                "reviewCreatedVersion": as_str(r.get("reviewCreatedVersion", "")),
                "at": as_str(r.get("at")),
                "thumbsUpCount": r.get("thumbsUpCount", 0),
                "userName": as_str(r.get("userName", "")),
                "replyContent": as_str(r.get("replyContent", "")),
                "repliedAt": as_str(r.get("repliedAt")),
            }
        )
    return {
        "app_id": app_id,
        "platform": platform,
        "source_csv": "live-scrape",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "reviews": out,
    }


def write_data_js() -> None:
    """data.js = 全部应用的内联合并镜像, file:// 双击打开也能切包/筛选/导出。"""
    try:
        index = json.loads((APPS_DIR / "index.json").read_text(encoding="utf-8")).get("apps", [])
    except Exception:
        index = []
    apps_inline = []
    for e in index:
        try:
            data = json.loads((APPS_DIR / Path(e["file"]).name).read_text(encoding="utf-8"))
        except Exception:
            continue
        entry = {k: e.get(k) for k in ("app_id", "platform", "title", "total", "generated_at")}
        entry["data"] = data
        apps_inline.append(entry)
    body = "\n".join(
        ["// 由 serve_reviews.py 自动写入 — 请勿手改"]
        + (
            ["window.REVIEWS_APPS = " + json.dumps({"apps": apps_inline}, ensure_ascii=False) + ";"]
            if apps_inline
            else []
        )
    ) + "\n"
    (TEMPLATE_DIR / "data.js").write_text(body, encoding="utf-8")


def persist(app_id: str, payload: dict) -> None:
    """多包 upsert: CSV + apps/<id>.json + index.json + data.js (file:// 回退)。"""
    cols = [
        "reviewId", "countries", "primary_country", "score", "content",
        "reviewCreatedVersion", "at", "thumbsUpCount", "userName",
        "replyContent", "repliedAt",
    ]
    csv_dir = CSV_DIR
    csv_dir.mkdir(parents=True, exist_ok=True)
    with (csv_dir / f"{app_id.replace('.', '_')}.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in payload["reviews"]:
            w.writerow([r[c] for c in cols])

    APPS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", app_id)
    (APPS_DIR / f"{safe}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    index_path = APPS_DIR / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")).get("apps", [])
    except Exception:
        index = []
    index = [e for e in index if e.get("app_id") != app_id]
    index.insert(
        0,
        {
            "app_id": app_id,
            "platform": payload.get("platform", "android"),
            "title": payload.get("title") or app_id,
            "total": len(payload.get("reviews", [])),
            "generated_at": payload.get("generated_at", ""),
            "file": f"apps/{safe}.json",
        },
    )
    index_path.write_text(
        json.dumps({"apps": index}, ensure_ascii=False), encoding="utf-8"
    )

    write_data_js()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ASSETS_DIR), **kwargs)

    def end_headers(self):
        # 静态资源禁缓存: 技能更新后页面代码始终最新
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if urlparse(self.path).path == "/api/scrape":
            self.handle_scrape()
        else:
            super().do_GET()

    def handle_scrape(self):
        q = parse_qs(urlparse(self.path).query)
        app_id = (q.get("app") or ["gmikhail.colorpicker"])[0].strip()
        try:
            per_country = int((q.get("count") or ["3000"])[0])
        except ValueError:
            per_country = 3000
        tier = (q.get("tier") or ["t1"])[0].strip().lower()
        markets = markets_for_tier(tier)
        if markets is T1_MARKETS and tier not in MARKET_TIERS:
            tier = "t1"
        platform = (q.get("platform") or ["android"])[0].strip().lower()
        if platform not in ("android", "ios"):
            platform = "android"
        if not app_id or len(app_id) > 120 or any(c in app_id for c in "/\\ \t"):
            self._ndjson_error(400, "invalid app id")
            return

        print(f"[scrape] {app_id} platform={platform} tier={tier} ({len(markets)} 国, 每国上限 {per_country})", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(obj: dict) -> None:
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            emit({"type": "start", "tier": tier, "markets": len(markets), "platform": platform})
            payload = scrape_to_payload(app_id, per_country, markets, emit, platform)
            payload["title"] = fetch_title(payload["app_id"], platform)
            emit({"type": "done", "payload": payload})
            persist(app_id, payload)
            print(f"[scrape] {app_id} 完成, 共 {len(payload['reviews'])} 条, 已落盘", flush=True)
        except (BrokenPipeError, ConnectionResetError):
            print("[scrape] 客户端中断", flush=True)
        except Exception as e:
            try:
                emit({"type": "fatal", "message": f"{type(e).__name__}: {e}"})
            except Exception:
                pass

    def _ndjson_error(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        self.wfile.write((json.dumps({"type": "fatal", "message": message}) + "\n").encode())
        self.wfile.flush()

    def log_message(self, fmt, *args):
        if "/api/scrape" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4318
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"评论看板服务已启动: http://localhost:{port}/dashboard/index.html")
    print("「拉取最新」按钮可用 (/api/scrape)。Ctrl+C 停止。")
    server.serve_forever()


if __name__ == "__main__":
    main()
