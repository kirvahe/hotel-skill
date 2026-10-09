"""Tests for bin/preflight.py: refuse to run on a missing, broken or template data folder.

All data here is made up.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "preflight.py"
TEMPLATE = Path(__file__).resolve().parent.parent / "taste-profile-template.md"

FILLED_PROFILE = """# Hotel Taste Profile

## Base
- Home: Testville

## TOP-3

| Hotel | City | Rating | What worked |
|---|---|---|---|
| Hotel Alpha | Testgrad | 10 | the best |
"""


def run(skill_dir: Path, settings: Path = None):
    extra = ["--settings", str(settings)] if settings else []
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skill-dir", str(skill_dir), *extra],
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.skill = self.root / "skill"
        self.skill.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_data_folder_stops_with_restore_message(self):  # Covers AE10
        result, out = run(self.skill)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(out["status"], "stop")
        self.assertIn("--data-dir", out["message"])

    def test_dangling_data_link_stops_with_restore_message(self):  # Covers AE10
        os.symlink(self.root / "gone", self.skill / "data")
        result, out = run(self.skill)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing folder", out["message"])
        self.assertIn("--data-dir", out["message"])

    def test_template_profile_stops(self):
        data = self.skill / "data"
        data.mkdir()
        (data / "taste-profile.md").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        result, out = run(self.skill)
        self.assertEqual(result.returncode, 1)
        self.assertIn("template", out["message"])

    def test_linked_folder_with_filled_profile_passes(self):
        real = self.root / "mydata"
        real.mkdir()
        (real / "taste-profile.md").write_text(FILLED_PROFILE, encoding="utf-8")
        os.symlink(real, self.skill / "data")
        result, out = run(self.skill)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["data_root"], str(real.resolve()))

    def test_real_directory_with_filled_profile_passes(self):
        data = self.skill / "data"
        data.mkdir()
        (data / "taste-profile.md").write_text(FILLED_PROFILE, encoding="utf-8")
        result, out = run(self.skill)
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(out["status"], "ok")


class GuardHookCheckTest(unittest.TestCase):
    """The guard hook (R21) must be installed before a search; a missing hook stops the run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name).resolve() / "skill"
        (self.skill / "data").mkdir(parents=True)
        (self.skill / "data" / "taste-profile.md").write_text(FILLED_PROFILE, encoding="utf-8")
        self.settings = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def skill_md(self, hook_path: str):
        command = f'[ -f "{hook_path}" ] || exit 0; exec python3 "{hook_path}"'
        (self.skill / "SKILL.md").write_text(
            f"---\nname: hotel\nhooks:\n  PreToolUse:\n    - matcher: \"^(Bash)$\"\n      hooks:\n"
            f"        - type: command\n          command: '{command}'\n---\n\n# Body\n", encoding="utf-8")

    def test_installed_guard_hook_passes(self):
        (self.skill / "bin").mkdir()
        (self.skill / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")
        self.skill_md(f"{self.skill}/bin/guard_hook.py")
        subprocess.run([sys.executable, str(SCRIPT.parent / "settings_hook.py"), "add", "--skill-dir", str(self.skill),
                        "--settings", str(self.settings)], check=True, capture_output=True)
        result, out = run(self.skill, self.settings)
        self.assertEqual((result.returncode, out["status"]), (0, "ok"), out)

    def test_skill_folder_with_a_space_in_its_path_passes(self):
        spaced = self.skill.parent / "A&B skills" / "hotel"
        (spaced / "bin").mkdir(parents=True)
        (spaced / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")
        (spaced / "data").symlink_to(self.skill / "data")
        self.skill, original = spaced, self.skill
        self.skill_md(f"{spaced}/bin/guard_hook.py")
        self.skill = original
        subprocess.run([sys.executable, str(SCRIPT.parent / "settings_hook.py"), "add", "--skill-dir", str(spaced),
                        "--settings", str(self.settings)], check=True, capture_output=True)
        result, out = run(spaced, self.settings)
        self.assertEqual((result.returncode, out["status"]), (0, "ok"), out)

    def test_guard_not_registered_in_settings_stops(self):
        (self.skill / "bin").mkdir()
        (self.skill / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")
        self.skill_md(f"{self.skill}/bin/guard_hook.py")
        result, out = run(self.skill, self.settings)
        self.assertEqual((result.returncode, out["status"]), (1, "stop"))
        self.assertIn("settings_hook.py add", out["message"])

    def test_guard_registered_with_an_older_matcher_stops(self):
        (self.skill / "bin").mkdir()
        (self.skill / "bin" / "guard_hook.py").write_text("# guard\n", encoding="utf-8")
        self.skill_md(f"{self.skill}/bin/guard_hook.py")
        command = f'[ -f "{self.skill}/bin/guard_hook.py" ] || exit 0; exec python3 "{self.skill}/bin/guard_hook.py"  # hotel-skill-guard'
        entry = {"matcher": "^(Bash|WebFetch|mcp__.+)$", "hooks": [{"type": "command", "command": command, "timeout": 10}]}
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [entry]}}), encoding="utf-8")
        result, out = run(self.skill, self.settings)
        self.assertEqual((result.returncode, out["status"]), (1, "stop"))
        self.assertIn("current tool matcher", out["message"])
        self.assertIn("settings_hook.py add", out["message"])

    def test_guard_hook_not_set_up_by_the_installer_stops(self):
        self.skill_md("__HOTEL_SKILL_DIR__/bin/guard_hook.py")
        result, out = run(self.skill)
        self.assertEqual(out["status"], "stop")
        self.assertIn("install.sh", out["message"])

    def test_missing_guard_hook_file_stops(self):
        self.skill_md("/nowhere/moved-skill/bin/guard_hook.py")
        result, out = run(self.skill)
        self.assertEqual((result.returncode, out["status"]), (1, "stop"))
        self.assertIn("/nowhere/moved-skill/bin/guard_hook.py", out["message"])

    def test_skill_md_without_the_guard_hook_stops(self):
        (self.skill / "SKILL.md").write_text("---\nname: hotel\n---\n\n# Body\n", encoding="utf-8")
        result, out = run(self.skill)
        self.assertEqual(out["status"], "stop")
        self.assertIn("guard", out["message"])


if __name__ == "__main__":
    unittest.main()
