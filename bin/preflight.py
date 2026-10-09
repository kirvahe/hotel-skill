#!/usr/bin/env python3
"""Check the skill's data folder before any search, review or analysis.

Usage:
    python3 preflight.py [--skill-dir DIR] [--settings FILE]

DIR defaults to the folder that contains this bin/ directory (the installed
skill). The data folder is DIR/data: a link to an existing folder or a real
directory are both fine.

Prints JSON {"status": "ok"|"stop", "message", "data_root", "warnings"}.
Exit 0 when the run may continue, 1 when it must stop and show the message.
A run stops when data/ is absent, links to a missing folder, has no
taste-profile.md, or the profile is still the unfilled template; and when
DIR/SKILL.md does not name an installed guard hook (bin/guard_hook.py, R21):
the hook command lets every call through when its file is gone, so this is
where a moved or hand-copied skill is caught. It also stops when the Claude Code
settings file (FILE, default ~/.claude/settings.json) does not register the guard
for this skill folder: only a settings-file hook covers the search subagents.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings_hook  # noqa: E402

PLACEHOLDER_PREFIXES = ("<!--", "_TBD", "{")
GUARD_PATH = re.compile(r"""([^\s"']*/bin/guard_hook\.py)""")


def top3_hotels(profile: str) -> int | None:
    """Number of real hotel rows under '## TOP-3', or None when there is no such heading."""
    lines = profile.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## TOP-3")), None)
    if start is None:
        return None
    count = 0
    seen_header = False
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if not line.lstrip().startswith("|"):
            continue
        first = line.strip().strip("|").split("|")[0].strip()
        if not seen_header:
            seen_header = True
            continue
        if not first or set(first) <= set("-: "):
            continue
        if not first.startswith(PLACEHOLDER_PREFIXES):
            count += 1
    return count


def guard_problem(skill_dir: Path, settings: Path = settings_hook.DEFAULT_SETTINGS) -> str | None:
    """Why the guard hook is not usable, or None. A skill folder without SKILL.md is not checked."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    paths = GUARD_PATH.findall(skill_md.read_text(encoding="utf-8"))
    reinstall = "Re-install with ./install.sh, which sets the guard hook's path."
    if not paths:
        return f"{skill_md} names no guard hook (bin/guard_hook.py). {reinstall}"
    if any("__HOTEL_SKILL_DIR__" in path for path in paths):
        return f"The guard hook in {skill_md} was never set up (the skill was copied by hand). {reinstall}"
    missing = [path for path in dict.fromkeys(paths) if not Path(path).is_file()]
    if missing:
        return f"The guard hook file is missing: {missing[0]} (was the skill folder moved?). {reinstall}"
    registered = settings_hook.status(settings, skill_dir.resolve())
    if registered != "ok":
        where = "for another skill folder" if registered == "other_skill_dir" else "yet"
        return (f"The guard hook is not registered in {settings} {where}. Without it the search agents are not "
                f"kept off Booking and Airbnb. Register it with: python3 {skill_dir.resolve()}/bin/settings_hook.py "
                f"add --skill-dir {skill_dir.resolve()}  (or re-install with ./install.sh --guard-in-settings)")
    return None


def check(skill_dir: Path, settings: Path = settings_hook.DEFAULT_SETTINGS) -> dict:
    data = skill_dir / "data"
    result = {"status": "stop", "message": "", "data_root": "", "warnings": []}
    reinstall = "Re-install with: ./install.sh --data-dir /path/to/your/hotel-data"

    problem = guard_problem(skill_dir, settings)
    if problem:
        result["message"] = problem
        return result

    if os.path.islink(data) and not data.exists():
        result["message"] = f"data/ links to a missing folder: {os.readlink(data)}. Restore that folder, or {reinstall[0].lower() + reinstall[1:]}"
        return result
    if not data.is_dir():
        result["message"] = f"No data folder at {data}. {reinstall}"
        return result

    root = data.resolve()
    result["data_root"] = str(root)
    profile_path = root / "taste-profile.md"
    if not profile_path.is_file():
        result["message"] = f"No taste-profile.md in {root}. Fill in the profile first, or {reinstall[0].lower() + reinstall[1:]}"
        return result

    rows = top3_hotels(profile_path.read_text(encoding="utf-8"))
    if rows == 0:
        result["message"] = (
            f"{profile_path} is still the unfilled template (no hotels under ## TOP-3). "
            "Fill in at least your TOP-3 hotels before using /hotel."
        )
        return result
    if rows is None:
        result["warnings"].append("taste-profile.md has no '## TOP-3' section; vibe anchors will be missing")

    result["status"] = "ok"
    result["message"] = f"data folder OK: {root}"
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the skill before any search, review or analysis.")
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--settings", default=str(settings_hook.DEFAULT_SETTINGS))
    args = parser.parse_args(argv[1:])
    result = check(Path(args.skill_dir).expanduser(), Path(args.settings).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
