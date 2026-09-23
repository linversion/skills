import importlib.util
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

            runtime = Path(temporary_directory) / "runtime"
            self.assertTrue((runtime / "monitor.py").is_file())
            self.assertTrue(
                (runtime / "When will Tibo reset.app" / "Contents" / "MacOS" / "AIHotNotifier").is_file()
            )

    def test_notifier_bundle_uses_the_fixed_user_visible_name(self):
        skill_root = SCRIPT.resolve().parents[1]
        app = skill_root / "assets" / "When will Tibo reset.app"
        info_path = app / "Contents" / "Info.plist"

        with info_path.open("rb") as handle:
            info = plistlib.load(handle)

        self.assertEqual(info["CFBundleDisplayName"], "When will Tibo reset")
        self.assertEqual(info["CFBundleName"], "Tibo reset mon")
        self.assertLessEqual(len(info["CFBundleName"]), 15)
        self.assertEqual(info["CFBundleVersion"], "3")
        self.assertEqual(manage.notifier_app_path().name, "When will Tibo reset.app")

    def test_skill_directory_and_frontmatter_use_the_new_slug(self):
        skill_root = SCRIPT.resolve().parents[1]
        self.assertEqual(skill_root.name, "when-will-tibo-reset")
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: when-will-tibo-reset", skill_text)
        self.assertIn("# When will Tibo reset", skill_text)


if __name__ == "__main__":
    unittest.main()
