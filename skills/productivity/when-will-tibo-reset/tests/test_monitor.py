import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor.py"
SPEC = importlib.util.spec_from_file_location("aihot_monitor", SCRIPT)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class FeedHandler(BaseHTTPRequestHandler):
    payload = {"events": []}
    user_agents = []

    def do_GET(self):
        self.__class__.user_agents.append(self.headers.get("User-Agent"))
        body = json.dumps(self.__class__.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class MonitorTests(unittest.TestCase):
    def setUp(self):
        FeedHandler.payload = {"schemaVersion": 1, "checkedAt": "2026-09-23T00:00:00Z", "events": []}
        FeedHandler.user_agents = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FeedHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.config_path = self.directory / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "url": "http://127.0.0.1:{}/feed".format(self.server.server_port),
                    "user_agent": "aihot-test/1.0",
                    "notifications": {"macos": True},
                    "webhooks": {},
                    "webhook_keywords": {},
                    "language": "zh",
                }
            ),
            encoding="utf-8",
        )
        self.notifications = []
        self.original_notify = monitor.notify
        monitor.notify = lambda config, title, local, webhook, **_options: self.notifications.append(
            {"title": title, "local": local, "webhook": webhook}
        ) or []

    def tearDown(self):
        monitor.notify = self.original_notify
        self.server.shutdown()
        self.server.server_close()
        self.temporary.cleanup()

    @staticmethod
    def event(event_id, status="announced", title="Tibo 预告将重置额度"):
        return {
            "id": event_id,
            "title": title,
            "status": status,
            "createdAt": "2026-09-23T01:00:00+08:00",
            "updatedAt": "2026-09-23T01:00:00+08:00",
            "url": "https://aihot.news/codex-reset",
        }

    def test_first_run_builds_silent_baseline(self):
        FeedHandler.payload["events"] = [self.event("event-1"), self.event("event-2")]
        self.assertEqual(monitor.run_check(self.config_path), 0)
        self.assertEqual(self.notifications, [])
        state = json.loads((self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertTrue(state["initialized"])
        self.assertEqual(set(state["events"]), {"event-1", "event-2"})
        self.assertEqual(FeedHandler.user_agents, ["aihot-test/1.0"])

    def test_new_and_updated_events_are_combined_into_one_notification(self):
        FeedHandler.payload["events"] = [self.event("event-1")]
        self.assertEqual(monitor.run_check(self.config_path), 0)

        updated = self.event("event-1", status="confirmed", title="Codex 额度重置已完成")
        updated["updatedAt"] = "2026-09-23T02:00:00+08:00"
        FeedHandler.payload["events"] = [updated, self.event("event-2")]
        self.assertEqual(monitor.run_check(self.config_path), 0)

        self.assertEqual(len(self.notifications), 1)
        message = self.notifications[0]["local"]
        self.assertIn("[更新] Codex 额度重置已完成 [announced → confirmed]", message)
        self.assertIn("[新增] Tibo 预告将重置额度 [announced]", message)

    def test_unchanged_feed_does_not_notify(self):
        FeedHandler.payload["events"] = [self.event("event-1")]
        self.assertEqual(monitor.run_check(self.config_path), 0)
        self.assertEqual(monitor.run_check(self.config_path), 0)
        self.assertEqual(self.notifications, [])

    def test_removed_then_reintroduced_event_is_not_treated_as_new(self):
        FeedHandler.payload["events"] = [self.event("event-1")]
        self.assertEqual(monitor.run_check(self.config_path), 0)
        FeedHandler.payload["events"] = []
        self.assertEqual(monitor.run_check(self.config_path), 0)
        FeedHandler.payload["events"] = [self.event("event-1")]
        self.assertEqual(monitor.run_check(self.config_path), 0)
        self.assertEqual(self.notifications, [])

    def test_feishu_keyword_is_included_in_webhook_payload(self):
        payload = monitor.webhook_payload(
            {"webhook_keywords": {"feishu": "Android"}},
            "feishu",
            "重置卡已发放",
            "这是一条测试通知。",
        )
        self.assertEqual(payload["msg_type"], "text")
        self.assertEqual(payload["content"]["text"], "Android · 重置卡已发放\n这是一条测试通知。")

    def test_macos_title_uses_tibo_prefix_without_changing_webhook_heading(self):
        self.assertEqual(monitor.format_macos_title("Banked reset granted"), "Tibo: Banked reset granted")
        self.assertEqual(monitor.format_macos_title("Tibo: 已发放重置卡"), "Tibo: 已发放重置卡")

        sent = []
        original_macos_notification = monitor.macos_notification
        monitor.notify = self.original_notify
        monitor.macos_notification = lambda _config, title, _body: sent.append(title)
        try:
            config = {"notifications": {"macos": True}, "webhooks": {}}
            monitor.notify(
                config,
                "AIHot Codex 重置动态（1）",
                "正文",
                "webhook 正文",
                channels={"macos"},
                webhook_title="动态标题",
                macos_title="动态标题",
            )
        finally:
            monitor.macos_notification = original_macos_notification
        self.assertEqual(sent, ["Tibo: 动态标题"])

    def test_source_uses_latest_post_url_then_falls_back_to_event_url(self):
        event = self.event("event-1")
        event["posts"] = [
            {"publishedAt": "2026-09-22T00:00:00+08:00", "url": "https://x.com/older"},
            {"publishedAt": "2026-09-23T00:00:00+08:00", "url": "https://x.com/latest"},
        ]
        change = {"kind": "new", "event": event, "previous": None}

        _local_body, details = monitor.build_messages([change], "en")
        self.assertIn("https://x.com/latest", details)
        self.assertNotIn("https://x.com/older", details)
        self.assertNotIn(event["url"], details)

        event["posts"][-1].pop("url")
        _local_body, details = monitor.build_messages([change], "en")
        self.assertIn(event["url"], details)

    def test_messages_show_post_text_without_scope_or_post_heading(self):
        event = self.event("event-1", title="动态标题")
        event["scope"] = "Plus、Pro、Business"
        event["presentation"] = {"scopeLabel": "Plus, Pro and Business"}
        event["type"] = "reset_credit"
        event["status"] = "confirmed"
        event["posts"] = [{
            "publishedAt": "2026-09-23T00:00:00+08:00",
            "stage": "发卡预告",
            "text": "中文 post 内容",
            "originalText": "English post content",
            "url": "https://x.com/latest",
        }]
        change = {"kind": "new", "event": event, "previous": None}

        for language, post_content, forbidden in (
            ("zh", "中文 post 内容", ("范围：", "最新动态")),
            ("en", "English post content", ("Scope:", "Latest:", "Latest post", "Banked reset announcement")),
        ):
            local_body, detailed_body = monitor.build_messages([change], language)
            self.assertIn(post_content, local_body)
            self.assertIn(post_content, detailed_body)
            self.assertIn(monitor.format_local_datetime(event["posts"][0]["publishedAt"]), local_body)
            self.assertIn(monitor.format_local_datetime(event["posts"][0]["publishedAt"]), detailed_body)
            for label in forbidden:
                self.assertNotIn(label, local_body)
                self.assertNotIn(label, detailed_body)

    def test_posted_timestamp_uses_local_timezone_and_minute_format(self):
        timestamp = "2026-09-23T02:23:37+08:00"
        expected = monitor.dt.datetime.fromisoformat(timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertEqual(monitor.format_local_datetime(timestamp), expected)
        self.assertEqual(monitor.format_local_datetime("2026-09-22T18:23:37Z"), expected)
        self.assertEqual(monitor.format_local_datetime("not-a-timestamp"), "")


if __name__ == "__main__":
    unittest.main()
