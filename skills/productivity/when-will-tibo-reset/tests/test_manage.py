import contextlib
import importlib.util
import io
import os
import plistlib
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "manage.py"
SPEC = importlib.util.spec_from_file_location("aihot_manage", SCRIPT)
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class ManageTests(unittest.TestCase):
    def test_changing_language_preserves_existing_configuration(self):
        for app_name in ("AIHot Notifier.app", "Custom Notifier.app"):
            with self.subTest(app_name=app_name), tempfile.TemporaryDirectory() as directory:
                with patch.dict(os.environ, {"AIHOT_MONITOR_HOME": directory}):
                    original = manage.default_config()
                    original["language"] = "en"
                    original["notifier_app"] = str(Path(directory) / "runtime" / app_name)
                    original["webhooks"]["feishu"] = "https://example.invalid/webhook"
                    manage.write_config(original)

                    with patch.object(manage, "is_loaded", return_value=True), \
                            patch.object(manage, "read_interval", return_value=3600), \
                            contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(manage.main(["configure", "--language", "zh"]), 0)

                    expected = dict(original, language="zh")
                    self.assertEqual(manage.load_config(), expected)

    def test_default_actor_is_generated_and_persisted_per_install(self):
        config = manage.default_config()
        actor_id = str(uuid.UUID(config["actor_id"]))

        self.assertEqual(
            config["user_agent"],
            "aihot-api/1.0 aihot-actor/{}".format(actor_id),
        )
        self.assertEqual(manage.default_config(config)["actor_id"], actor_id)
        self.assertNotEqual(manage.default_config()["actor_id"], actor_id)

    def test_replaces_legacy_fixed_installation_user_agent(self):
        previous = "aihot-api/1.0 aihot-actor/{}".format(uuid.uuid4())
        config = manage.default_config({"user_agent": previous})

        self.assertNotEqual(config["user_agent"], previous)
        self.assertEqual(
            config["user_agent"],
            "aihot-api/1.0 aihot-actor/{}".format(config["actor_id"]),
        )

    def test_preserves_an_explicit_custom_user_agent(self):
        config = manage.default_config({"user_agent": "my-monitor/2.0"})

        self.assertEqual(config["user_agent"], "my-monitor/2.0")
        self.assertEqual(config["actor_id"], "")

    def test_copy_runtime_installs_bundled_notifier_without_compiling(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(os.environ, {"AIHOT_MONITOR_HOME": temporary_directory}):
                manage.copy_runtime()
                manage.copy_runtime()

            runtime = Path(temporary_directory) / "runtime"
            self.assertTrue((runtime / "monitor.py").is_file())
            self.assertTrue(
                (runtime / "When will Tibo reset.app" / "Contents" / "MacOS" / "AIHotNotifier").is_file()
            )

    def test_reinstall_preserves_runtime_links_to_skill_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            script = runtime / "monitor.py"
            app = runtime / "When will Tibo reset.app"
            source_script = SCRIPT.with_name("monitor.py")
            source_app = SCRIPT.parents[1] / "assets" / app.name
            script.symlink_to(source_script)
            app.symlink_to(source_app, target_is_directory=True)
            original_content = source_script.read_bytes()
            original_mode = source_script.stat().st_mode

            with patch.dict(os.environ, {"AIHOT_MONITOR_HOME": directory}):
                manage.copy_runtime()
                manage.copy_runtime()

            self.assertTrue(script.is_symlink())
            self.assertTrue(app.is_symlink())
            self.assertTrue(script.samefile(source_script))
            self.assertTrue(app.samefile(source_app))
            self.assertEqual(source_script.read_bytes(), original_content)
            self.assertEqual(source_script.stat().st_mode, original_mode)

    def test_notifier_bundle_uses_the_fixed_user_visible_name(self):
        skill_root = SCRIPT.resolve().parents[1]
        app = skill_root / "assets" / "When will Tibo reset.app"
        info_path = app / "Contents" / "Info.plist"

        with info_path.open("rb") as handle:
            info = plistlib.load(handle)

        self.assertEqual(info["CFBundleDisplayName"], "When will Tibo reset")
        self.assertEqual(info["CFBundleName"], "Tibo reset mon")
        self.assertLessEqual(len(info["CFBundleName"]), 15)
        self.assertEqual(info["CFBundleVersion"], "4")
        self.assertEqual(manage.notifier_app_path().name, "When will Tibo reset.app")

    def test_skill_directory_and_frontmatter_use_the_new_slug(self):
        skill_root = SCRIPT.resolve().parents[1]
        self.assertEqual(skill_root.name, "when-will-tibo-reset")
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: when-will-tibo-reset", skill_text)
        self.assertIn("# When will Tibo reset", skill_text)


if __name__ == "__main__":
    unittest.main()
