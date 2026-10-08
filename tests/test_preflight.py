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


def run(skill_dir: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skill-dir", str(skill_dir)],
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


if __name__ == "__main__":
    unittest.main()
