#!/usr/bin/env python3
"""Poll AIHot reset events and notify configured destinations."""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_TIMEOUT = 20


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path, default=None):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def atomic_write_json(path, payload, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def log(level, message, **fields):
    record = {"time": utc_now(), "level": level, "message": message}
    record.update(fields)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)


def fetch_feed(config):
    request = urllib.request.Request(
        config["url"],
        headers={
            "User-Agent": config["user_agent"],
            "Accept": "application/json",
        },
        method="GET",
    )
    timeout = int(config.get("timeout_seconds", DEFAULT_TIMEOUT))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("API response must contain an events array")
    for event in payload["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
            raise ValueError("Every event must contain a non-empty string id")
    return payload


def event_digest(event):
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_record(event):
    return {
        "hash": event_digest(event),
        "title": str(event.get("title") or event.get("label") or "未命名动态"),
        "status": str(event.get("status") or ""),
        "updated_at": str(event.get("updatedAt") or event.get("createdAt") or ""),
    }


def find_changes(events, previous_records):
    changes = []
    merged_records = dict(previous_records)
    for event in events:
        event_id = event["id"]
        current = event_record(event)
        previous = previous_records.get(event_id)
        previous_hash = previous.get("hash") if isinstance(previous, dict) else previous
        if previous is None:
            changes.append({"kind": "new", "event": event, "previous": None})
        elif previous_hash != current["hash"]:
            changes.append({"kind": "updated", "event": event, "previous": previous})
        merged_records[event_id] = current
    changes.sort(
        key=lambda item: str(
            item["event"].get("updatedAt") or item["event"].get("createdAt") or ""
        )
    )
    return changes, merged_records


def normalize_language(language):
    return "en" if str(language or "zh").strip().lower() in ("en", "english") else "zh"


def display_event_title(event, language="zh"):
    if normalize_language(language) == "zh":
        return str(event.get("title") or event.get("label") or "未命名动态")

    event_type = str(event.get("type") or "")
    status = str(event.get("status") or "")
    if event_type == "reset_credit":
        return "Banked reset granted" if status == "confirmed" else "Tibo announced a banked reset"
    if event_type == "direct_reset":
        return "Codex usage limits reset" if status == "confirmed" else "Tibo announced a Codex reset"

    english_title = str(event.get("englishTitle") or event.get("title_en") or "").strip()
    if english_title:
        return english_title
    return "{} update".format(event_type.replace("_", " ").title() or "Codex reset")


def status_text(status, language):
    if normalize_language(language) == "zh":
        return str(status or "")
    translations = {
        "announced": "announced",
        "confirmed": "confirmed",
    }
    return translations.get(str(status or ""), str(status or "unknown"))


def latest_post(event):
    posts = event.get("posts") or []
    if not posts:
        return {}
    return max(posts, key=lambda post: str(post.get("publishedAt") or ""))


def format_local_datetime(value):
    timestamp = str(value or "").strip()
    if not timestamp:
        return ""
    if timestamp.endswith(("Z", "z")):
        timestamp = timestamp[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(timestamp)
    except ValueError:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def posted_line(post, language):
    posted_at = format_local_datetime(post.get("publishedAt"))
    if not posted_at:
        return ""
    return "Posted: {}".format(posted_at) if language == "en" else "发布时间：{}".format(posted_at)


def post_text(post, language):
    if normalize_language(language) == "en":
        value = post.get("originalText") or post.get("fullOriginalText") or ""
        if any("\u4e00" <= character <= "\u9fff" for character in str(value)):
            return ""
        return str(value).strip()
    return str(post.get("text") or "").strip()


def schedule_text(schedule, language):
    if not isinstance(schedule, dict):
        return ""
    if normalize_language(language) == "zh":
        return str(schedule.get("label") or "").strip()
    start = str(schedule.get("from") or "").strip()
    end = str(schedule.get("through") or "").strip()
    if not start and not end:
        return ""
    precision = str(schedule.get("precision") or "")
    if start and end and start != end:
        return "Expected window: {} to {}".format(start, end)
    label = "Approximate time" if precision == "approximate" else "Scheduled time"
    return "{}: {}".format(label, start or end)


def change_line(change, language="zh"):
    event = change["event"]
    english = normalize_language(language) == "en"
    prefix = ("New" if change["kind"] == "new" else "Updated") if english else ("新增" if change["kind"] == "new" else "更新")
    title = display_event_title(event, language)
    status = str(event.get("status") or "")
    previous = change.get("previous")
    previous_status = previous.get("status") if isinstance(previous, dict) else ""
    if change["kind"] == "updated" and previous_status and status and previous_status != status:
        status_label = "{} → {}".format(
            status_text(previous_status, language), status_text(status, language)
        )
    else:
        status_label = status_text(status, language)
    suffix = " [{}]".format(status_label) if status_label else ""
    return "[{}] {}{}".format(prefix, title, suffix)


def build_messages(changes, language="zh"):
    language = normalize_language(language)
    lines = [change_line(change, language) for change in changes]
    shown_event_count = min(len(lines), 4 if language == "en" else 5)
    shown = lines[:shown_event_count]
    if changes:
        latest_event = changes[-1]["event"]
        post = latest_post(latest_event)
        excerpt = post_text(post, language)
        if excerpt:
            shown.append(excerpt[:180])
        posted = posted_line(post, language)
        if posted:
            shown.append(posted)
        post_url = str(post.get("url") or latest_event.get("url") or "").strip()
        if post_url:
            label = "Source" if language == "en" else "来源"
            shown.append("{}: {}".format(label, post_url) if language == "en" else "{}：{}".format(label, post_url))
    if len(lines) > shown_event_count:
        remaining = len(lines) - shown_event_count
        if remaining:
            shown.append("{} more updates".format(remaining) if language == "en" else "另有 {} 条动态".format(remaining))
    local_body = "\n".join(shown)

    detailed = (
        ["AIHot detected {} Codex reset update(s):".format(len(changes))]
        if language == "en"
        else ["AIHot 检测到 {} 条 Codex 重置动态：".format(len(changes))]
    )
    for change in changes[:10]:
        event = change["event"]
        detailed.append(change_line(change, language))
        schedule = event.get("schedule") if isinstance(event.get("schedule"), dict) else {}
        schedule_label = schedule_text(schedule, language)
        if schedule_label:
            detailed.append(schedule_label)
        post = latest_post(event)
        excerpt = post_text(post, language)
        if excerpt:
            detailed.append(excerpt)
        posted = posted_line(post, language)
        if posted:
            detailed.append(posted)
        url = str(post.get("url") or event.get("url") or "").strip()
        if url:
            label = "Source" if language == "en" else "来源"
            detailed.append("{}: {}".format(label, url) if language == "en" else "{}：{}".format(label, url))
    if len(changes) > 10:
        remaining = len(changes) - 10
        detailed.append(
            "See AIHot for {} more updates.".format(remaining)
            if language == "en"
            else "其余 {} 条请查看 AIHot。".format(remaining)
        )
    return local_body, "\n".join(detailed)


def macos_notification(config, title, body):
    configured_path = str(config.get("notifier_app") or "").strip()
    app_path = Path(configured_path) if configured_path else Path(__file__).resolve().parent / "When will Tibo reset.app"
    executable = app_path / "Contents" / "MacOS" / "AIHotNotifier"
    if not executable.is_file():
        raise FileNotFoundError("Native notification helper is missing; reinstall the monitor")
    with tempfile.TemporaryDirectory(prefix="aihot-notify-") as temporary:
        status_path = Path(temporary) / "status.txt"
        subprocess.run(
            [
                "/usr/bin/open",
                "-n",
                "-W",
                str(app_path),
                "--args",
                title,
                body,
                str(status_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        status = status_path.read_text(encoding="utf-8").strip() if status_path.exists() else ""
        if status != "submitted":
            raise RuntimeError(status or "native notifier exited without a delivery status")


def format_macos_title(title):
    heading = str(title or "").strip()
    if heading.lower().startswith("tibo:"):
        return heading
    return "Tibo: {}".format(heading) if heading else "Tibo"


def post_json(url, payload, timeout):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8", errors="replace")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError("webhook returned HTTP {}".format(response.status))
    if response_body:
        try:
            result = json.loads(response_body)
        except json.JSONDecodeError:
            return
        error_code = result.get("code", result.get("errcode", result.get("StatusCode", 0)))
        if error_code not in (None, 0, "0"):
            raise RuntimeError("webhook rejected message with code {}".format(error_code))


def webhook_payload(config, channel, title, body):
    keyword = str(config.get("webhook_keywords", {}).get(channel) or "").strip()
    heading = str(title or "").strip()
    if keyword:
        heading = "{} · {}".format(keyword, heading) if heading else keyword
    parts = [heading] if heading else []
    if body:
        parts.append(str(body).strip())
    message = "\n".join(part for part in parts if part)
    if channel == "feishu":
        return {"msg_type": "text", "content": {"text": message}}
    return {"msgtype": "text", "text": {"content": message}}


def notify(config, title, local_body, webhook_body, channels=None, webhook_title=None, macos_title=None):
    errors = []
    selected = set(channels or ("macos", "feishu", "dingtalk", "wecom"))
    notifications = config.get("notifications", {})
    if "macos" in selected and notifications.get("macos", True):
        try:
            macos_notification(config, format_macos_title(macos_title or title), local_body)
            log("info", "macOS notification submitted")
        except Exception as exc:
            errors.append("macos: {}".format(exc))
            log("error", "macOS notification failed", error=str(exc))

    timeout = int(config.get("timeout_seconds", DEFAULT_TIMEOUT))
    webhooks = config.get("webhooks", {})
    for channel in ("feishu", "dingtalk", "wecom"):
        if channel not in selected:
            continue
        url = str(webhooks.get(channel) or "").strip()
        if not url:
            continue
        try:
            post_json(url, webhook_payload(config, channel, webhook_title or title, webhook_body), timeout)
            log("info", "webhook notification submitted", channel=channel)
        except Exception as exc:
            errors.append("{}: {}".format(channel, exc))
            log("error", "webhook notification failed", channel=channel, error=str(exc))
    return errors


def run_check(config_path):
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("Missing or invalid config: {}".format(config_path))
    state_path = config_path.parent / "state.json"
    state = load_json(state_path, default={})
    previous_records = state.get("events", {}) if isinstance(state, dict) else {}
    if not isinstance(previous_records, dict):
        previous_records = {}

    feed = fetch_feed(config)
    events = feed["events"]
    initialized = bool(state.get("initialized")) if isinstance(state, dict) else False
    changes, merged_records = find_changes(events, previous_records)
    next_state = {
        "schema_version": 1,
        "initialized": True,
        "initialized_at": state.get("initialized_at", utc_now()) if isinstance(state, dict) else utc_now(),
        "last_checked_at": utc_now(),
        "feed_checked_at": feed.get("checkedAt"),
        "events": merged_records,
    }
    atomic_write_json(state_path, next_state)

    if not initialized:
        log("info", "baseline initialized", event_count=len(events))
        return 0
    if not changes:
        log("info", "no changes", event_count=len(events))
        return 0

    language = normalize_language(config.get("language"))
    local_body, webhook_body = build_messages(changes, language)
    latest_event = changes[-1]["event"]
    webhook_title = display_event_title(latest_event, language)
    if len(changes) > 1:
        webhook_title = (
            "{} and {} other update(s)".format(webhook_title, len(changes) - 1)
            if language == "en"
            else "{} 等 {} 条动态".format(webhook_title, len(changes))
        )
    notification_title = (
        "AIHot Codex reset update(s) ({})".format(len(changes))
        if language == "en"
        else "AIHot Codex 重置动态（{}）".format(len(changes))
    )
    errors = notify(
        config,
        notification_title,
        local_body,
        webhook_body,
        webhook_title=webhook_title,
        macos_title=webhook_title,
    )
    log("info", "changes detected", change_count=len(changes), delivery_errors=len(errors))
    return 2 if errors else 0


def test_notification(config_path, channels=None):
    config = load_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("Missing or invalid config: {}".format(config_path))
    if normalize_language(config.get("language")) == "en":
        title = "AIHot Monitor Test"
        text = "This is a test notification. AIHot Codex reset monitoring is connected."
    else:
        title = "AIHot 监控测试"
        text = "这是一条测试通知。AIHot Codex 重置动态监控已连接。"
    errors = notify(config, title, text, text, channels=channels, macos_title=title)
    return 2 if errors else 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--test-notification", action="store_true")
    parser.add_argument(
        "--channel",
        action="append",
        choices=("macos", "feishu", "dingtalk", "wecom"),
        help="limit a test notification to one or more channels",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.test_notification:
            return test_notification(args.config.expanduser().resolve(), channels=args.channel)
        return run_check(args.config.expanduser().resolve())
    except urllib.error.HTTPError as exc:
        log("error", "HTTP request failed", status=exc.code, error=str(exc))
    except urllib.error.URLError as exc:
        log("error", "network request failed", error=str(exc.reason))
    except Exception as exc:
        log("error", "monitor failed", error=str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
