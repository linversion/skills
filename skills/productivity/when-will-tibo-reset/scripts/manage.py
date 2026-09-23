#!/usr/bin/env python3
"""Install and manage the AIHot Codex reset monitor LaunchAgent."""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


LABEL = "com.aihot.codex-reset-monitor"
DEFAULT_URL = "https://aihot.news/api/v1/codex-resets"
DEFAULT_USER_AGENT = "aihot-api/1.0"
ACTOR_USER_AGENT_PREFIX = DEFAULT_USER_AGENT + " aihot-actor/"


def data_dir():
    override = os.environ.get("AIHOT_MONITOR_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / "Library" / "Application Support" / "AIHot Codex Reset Monitor"


def launch_agent_path():
    override = os.environ.get("AIHOT_MONITOR_LAUNCH_AGENTS")
    root = Path(override).expanduser().resolve() if override else Path.home() / "Library" / "LaunchAgents"
    return root / (LABEL + ".plist")


def config_path():
    return data_dir() / "config.json"


def runtime_script_path():
    return data_dir() / "runtime" / "monitor.py"


def notifier_app_path():
    return data_dir() / "runtime" / "When will Tibo reset.app"


def load_config():
    try:
        with config_path().open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_config(config):
    payload = (json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(config_path(), payload, 0o600)


def default_config(existing=None):
    existing = existing or {}
    actor_id = str(existing.get("actor_id") or "").strip()
    user_agent = str(existing.get("user_agent") or "").strip()

    if actor_id:
        user_agent = user_agent or ACTOR_USER_AGENT_PREFIX + actor_id
    elif user_agent.startswith(ACTOR_USER_AGENT_PREFIX):
        # Replace actor IDs from older skill versions with a per-install ID.
        actor_id = str(uuid.uuid4())
        user_agent = ACTOR_USER_AGENT_PREFIX + actor_id
    elif not user_agent:
        actor_id = str(uuid.uuid4())
        user_agent = ACTOR_USER_AGENT_PREFIX + actor_id

    return {
        "schema_version": 1,
        "language": str(existing.get("language", "zh")),
        "url": existing.get("url", DEFAULT_URL),
        "actor_id": actor_id,
        "user_agent": user_agent,
        "timeout_seconds": int(existing.get("timeout_seconds", 20)),
        "notifier_app": str(notifier_app_path()),
        "notifications": {
            "macos": bool(existing.get("notifications", {}).get("macos", True)),
        },
        "webhooks": {
            "feishu": str(existing.get("webhooks", {}).get("feishu", "")),
            "dingtalk": str(existing.get("webhooks", {}).get("dingtalk", "")),
            "wecom": str(existing.get("webhooks", {}).get("wecom", "")),
        },
        "webhook_keywords": {
            "feishu": str(existing.get("webhook_keywords", {}).get("feishu", "")),
            "dingtalk": str(existing.get("webhook_keywords", {}).get("dingtalk", "")),
            "wecom": str(existing.get("webhook_keywords", {}).get("wecom", "")),
        },
    }


def apply_webhook_options(config, args):
    webhooks = config.setdefault("webhooks", {})
    environment_names = {
        "feishu": "AIHOT_FEISHU_WEBHOOK",
        "dingtalk": "AIHOT_DINGTALK_WEBHOOK",
        "wecom": "AIHOT_WECOM_WEBHOOK",
    }
    for channel, environment_name in environment_names.items():
        argument_value = getattr(args, channel + "_webhook", None)
        environment_value = os.environ.get(environment_name)
        if argument_value is not None:
            webhooks[channel] = argument_value.strip()
        elif environment_value is not None:
            webhooks[channel] = environment_value.strip()
        if getattr(args, "clear_" + channel, False):
            webhooks[channel] = ""
            config.setdefault("webhook_keywords", {})[channel] = ""

    keyword_environment_names = {
        "feishu": "AIHOT_FEISHU_KEYWORD",
        "dingtalk": "AIHOT_DINGTALK_KEYWORD",
        "wecom": "AIHOT_WECOM_KEYWORD",
    }
    keywords = config.setdefault("webhook_keywords", {})
    for channel, environment_name in keyword_environment_names.items():
        argument_value = getattr(args, channel + "_keyword", None)
        environment_value = os.environ.get(environment_name)
        if argument_value is not None:
            keywords[channel] = argument_value.strip()
        elif environment_value is not None:
            keywords[channel] = environment_value.strip()


def launch_domain():
    return "gui/{}".format(os.getuid())


def launch_target():
    return "{}/{}".format(launch_domain(), LABEL)


def launchctl(*arguments, check=True, capture=False):
    return subprocess.run(
        ["/bin/launchctl"] + list(arguments),
        check=check,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def is_loaded():
    result = launchctl("print", launch_target(), check=False, capture=True)
    return result.returncode == 0


def write_plist(interval_seconds):
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            str(runtime_script_path()),
            "--config",
            str(config_path()),
        ],
        "RunAtLoad": True,
        "StartInterval": int(interval_seconds),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(directory / "monitor.stdout.log"),
        "StandardErrorPath": str(directory / "monitor.stderr.log"),
    }
    atomic_write(launch_agent_path(), plistlib.dumps(plist, sort_keys=True), 0o644)


def copy_runtime():
    source = Path(__file__).with_name("monitor.py")
    destination = runtime_script_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    os.chmod(destination, 0o700)
    install_bundled_notifier_app()


def install_bundled_notifier_app():
    skill_root = Path(__file__).resolve().parent.parent
    source = skill_root / "assets" / "When will Tibo reset.app"
    executable = source / "Contents" / "MacOS" / "AIHotNotifier"
    if not source.is_dir() or not executable.is_file():
        raise FileNotFoundError("Bundled assets/When will Tibo reset.app is missing or incomplete")

    app = notifier_app_path()
    if app.exists():
        shutil.rmtree(app)
    shutil.copytree(source, app)


def run_monitor(test=False, channel=None):
    command = [sys.executable, str(runtime_script_path()), "--config", str(config_path())]
    if test:
        command.append("--test-notification")
    if channel:
        command.extend(["--channel", channel])
    return subprocess.run(command, check=False).returncode


def redact_status(config):
    state_path = data_dir() / "state.json"
    state = {}
    try:
        with state_path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        pass
    webhooks = config.get("webhooks", {})
    keywords = config.get("webhook_keywords", {})
    return {
        "installed": launch_agent_path().exists(),
        "loaded": is_loaded(),
        "interval_seconds": read_interval(),
        "macos_notifications": bool(config.get("notifications", {}).get("macos", True)),
        "webhooks_configured": {
            "feishu": bool(webhooks.get("feishu")),
            "dingtalk": bool(webhooks.get("dingtalk")),
            "wecom": bool(webhooks.get("wecom")),
        },
        "language": config.get("language", "zh"),
        "webhook_keywords_configured": {
            "feishu": bool(keywords.get("feishu")),
            "dingtalk": bool(keywords.get("dingtalk")),
            "wecom": bool(keywords.get("wecom")),
        },
        "baseline_initialized": bool(state.get("initialized")),
        "last_checked_at": state.get("last_checked_at"),
        "known_event_count": len(state.get("events", {})) if isinstance(state.get("events"), dict) else 0,
        "data_directory": str(data_dir()),
    }


def read_interval():
    try:
        with launch_agent_path().open("rb") as handle:
            plist = plistlib.load(handle)
        return plist.get("StartInterval")
    except FileNotFoundError:
        return None


def command_install(args):
    config = default_config(load_config())
    if args.language:
        config["language"] = args.language
    config["url"] = args.url
    if args.user_agent:
        config["user_agent"] = args.user_agent.strip()
        config["actor_id"] = ""
    if args.disable_macos:
        config["notifications"]["macos"] = False
    apply_webhook_options(config, args)
    write_config(config)
    copy_runtime()
    baseline_result = run_monitor()
    if baseline_result != 0:
        print("Baseline request failed; LaunchAgent was not changed.", file=sys.stderr)
        return baseline_result

    if is_loaded():
        launchctl("bootout", launch_target(), check=False)
    write_plist(args.interval)
    result = launchctl("bootstrap", launch_domain(), str(launch_agent_path()), check=False, capture=True)
    if result.returncode != 0:
        print(result.stderr.strip() or "launchctl bootstrap failed", file=sys.stderr)
        return result.returncode or 1
    print(json.dumps(redact_status(config), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_configure(args):
    config = default_config(load_config())
    if args.language:
        config["language"] = args.language
    if args.enable_macos:
        config["notifications"]["macos"] = True
    if args.disable_macos:
        config["notifications"]["macos"] = False
    apply_webhook_options(config, args)
    write_config(config)
    print(json.dumps(redact_status(config), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_status(_args):
    print(json.dumps(redact_status(default_config(load_config())), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_check(_args):
    if not runtime_script_path().exists() or not config_path().exists():
        print("Monitor is not installed. Run: manage.py install", file=sys.stderr)
        return 1
    return run_monitor()


def command_test(args):
    if not runtime_script_path().exists() or not config_path().exists():
        print("Monitor is not installed. Run: manage.py install", file=sys.stderr)
        return 1
    return run_monitor(test=True, channel=args.channel)


def command_stop(_args):
    if is_loaded():
        result = launchctl("bootout", launch_target(), check=False, capture=True)
        if result.returncode != 0:
            print(result.stderr.strip() or "launchctl bootout failed", file=sys.stderr)
            return result.returncode or 1
    print("AIHot monitor stopped.")
    return 0


def command_uninstall(args):
    result = command_stop(args)
    if result != 0:
        return result
    try:
        launch_agent_path().unlink()
    except FileNotFoundError:
        pass
    if args.purge and data_dir().exists():
        shutil.rmtree(data_dir())
        print("LaunchAgent and local monitor data removed.")
    else:
        print("LaunchAgent removed; local config and state were preserved.")
    return 0


def add_webhook_arguments(parser):
    parser.add_argument("--feishu-webhook")
    parser.add_argument("--dingtalk-webhook")
    parser.add_argument("--wecom-webhook")
    parser.add_argument("--feishu-keyword")
    parser.add_argument("--dingtalk-keyword")
    parser.add_argument("--wecom-keyword")
    parser.add_argument("--clear-feishu", action="store_true")
    parser.add_argument("--clear-dingtalk", action="store_true")
    parser.add_argument("--clear-wecom", action="store_true")


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="initialize and load the hourly LaunchAgent")
    install.add_argument("--url", default=DEFAULT_URL)
    install.add_argument("--user-agent", help="override the default per-install API user agent")
    install.add_argument("--interval", type=int, default=3600)
    install.add_argument("--language", choices=("zh", "en"), help="notification language")
    install.add_argument("--disable-macos", action="store_true")
    add_webhook_arguments(install)
    install.set_defaults(handler=command_install)

    configure = subparsers.add_parser("configure", help="update notification destinations")
    configure.add_argument("--language", choices=("zh", "en"), help="notification language")
    macos_group = configure.add_mutually_exclusive_group()
    macos_group.add_argument("--enable-macos", action="store_true")
    macos_group.add_argument("--disable-macos", action="store_true")
    add_webhook_arguments(configure)
    configure.set_defaults(handler=command_configure)

    status = subparsers.add_parser("status", help="show redacted monitor status")
    status.set_defaults(handler=command_status)
    check = subparsers.add_parser("check", help="poll immediately")
    check.set_defaults(handler=command_check)
    test = subparsers.add_parser("test-notification", help="send a test notification")
    test.add_argument("--channel", choices=("macos", "feishu", "dingtalk", "wecom"))
    test.set_defaults(handler=command_test)
    stop = subparsers.add_parser("stop", help="unload but preserve the LaunchAgent file")
    stop.set_defaults(handler=command_stop)
    uninstall = subparsers.add_parser("uninstall", help="unload and remove the LaunchAgent")
    uninstall.add_argument("--purge", action="store_true")
    uninstall.set_defaults(handler=command_uninstall)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if getattr(args, "interval", 3600) < 60:
        print("Interval must be at least 60 seconds.", file=sys.stderr)
        return 2
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
