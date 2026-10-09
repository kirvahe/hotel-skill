"""Tests for bin/settings_hook.py: the guard hook entry in a Claude Code settings file.

Every settings file here is a temporary one; the user's own settings are never read.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import guard_hook  # noqa: E402
import settings_hook  # noqa: E402

OLD_MATCHER = "^(Bash|WebFetch|mcp__.+)$"  # before 1.2: started the guard before every MCP tool

OTHER = {
    "model": "opus",
    "permissions": {"allow": ["Bash(git status)"]},
    "hooks": {
        "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "/x/sync.sh", "async": True}]}],
        "PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "/x/lint.sh"}]}],
    },
}


class SettingsHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.settings = self.root / "claude" / "settings.json"
        self.skill = self.root / "skills" / "hotel"
        (self.skill / "bin").mkdir(parents=True)
        (self.skill / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(BIN / "settings_hook.py"), *args, "--settings", str(self.settings)],
                              capture_output=True, text=True)

    def backups(self):
        return sorted(self.settings.parent.glob("settings.json.bak-hotel-*"))

    def ours(self):
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        return [hook for group in data.get("hooks", {}).get("PreToolUse", []) for hook in group["hooks"]
                if settings_hook.MARKER in hook.get("command", "")]

    def test_add_to_a_missing_file_creates_it(self):
        result = self.cli("add", "--skill-dir", str(self.skill))
        self.assertEqual(result.returncode, 0, result.stderr)
        [hook] = self.ours()
        self.assertIn(f'"{self.skill}/bin/guard_hook.py"', hook["command"])
        self.assertEqual(self.backups(), [])

    def test_add_keeps_everything_else_and_backs_up_first(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps(OTHER), encoding="utf-8")
        self.cli("add", "--skill-dir", str(self.skill))
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual((data["model"], data["permissions"]), (OTHER["model"], OTHER["permissions"]))
        self.assertEqual(data["hooks"]["SessionStart"], OTHER["hooks"]["SessionStart"])
        self.assertIn({"matcher": "Write", "hooks": [{"type": "command", "command": "/x/lint.sh"}]}, data["hooks"]["PreToolUse"])
        self.assertEqual(len(self.ours()), 1)
        [backup] = self.backups()
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), OTHER)

    def test_adding_twice_changes_nothing(self):
        self.cli("add", "--skill-dir", str(self.skill))
        before = self.settings.read_text(encoding="utf-8")
        result = self.cli("add", "--skill-dir", str(self.skill))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(self.backups(), [])
        self.assertIn("already", result.stdout)

    def test_a_new_skill_folder_replaces_the_old_entry(self):
        self.cli("add", "--skill-dir", str(self.skill))
        moved = self.root / "elsewhere" / "hotel"
        (moved / "bin").mkdir(parents=True)
        (moved / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")
        self.cli("add", "--skill-dir", str(moved))
        [hook] = self.ours()
        self.assertIn(str(moved), hook["command"])

    def test_remove_takes_out_only_the_guard(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps(OTHER), encoding="utf-8")
        self.cli("add", "--skill-dir", str(self.skill))
        self.cli("remove")
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["hooks"], OTHER["hooks"])

    def test_a_settings_file_that_is_not_json_is_left_alone(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        result = self.cli("add", "--skill-dir", str(self.skill))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")
        self.assertIn("not valid JSON", result.stderr)
        self.assertEqual(settings_hook.status(self.settings, self.skill), "missing")
        with self.assertRaises(settings_hook.SettingsFileError):
            settings_hook.remove(self.settings)

    def test_status(self):
        self.assertEqual(settings_hook.status(self.settings, self.skill), "missing")
        self.cli("add", "--skill-dir", str(self.skill))
        self.assertEqual(settings_hook.status(self.settings, self.skill), "ok")
        self.assertEqual(settings_hook.status(self.settings, self.root / "other" / "hotel"), "other_skill_dir")

    def test_an_entry_with_an_older_matcher_is_reported_and_add_updates_it(self):
        self.settings.parent.mkdir(parents=True)
        old = {"matcher": OLD_MATCHER, "hooks": [{"type": "command", "command": settings_hook.command(self.skill),
                                                   "timeout": 10}]}
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [old]}}), encoding="utf-8")
        self.assertEqual(settings_hook.status(self.settings, self.skill), "old_matcher")
        result = self.cli("add", "--skill-dir", str(self.skill))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(settings_hook.status(self.settings, self.skill), "ok")
        groups = json.loads(self.settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual([group["matcher"] for group in groups], [guard_hook.MATCHER])
        self.assertEqual(len(self.backups()), 1)

    def test_the_skill_md_hook_is_the_settings_entry(self):
        # One command string in both places: Claude Code then runs the guard once per call, not twice.
        skill_md = (BIN.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^\s*command: '(.*)'$", skill_md, re.M),
                         [settings_hook.command(Path("__HOTEL_SKILL_DIR__"))])
        self.assertEqual(re.findall(r'^\s*- matcher: "(.*)"$', skill_md, re.M), [settings_hook.matcher()])

    def test_the_command_lets_calls_through_when_the_hook_file_is_gone(self):
        command = settings_hook.command(self.root / "gone" / "hotel")
        result = subprocess.run(["sh", "-c", command], input="{}", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
