#!/usr/bin/env python3
"""Register the /hotel guard hook in a Claude Code settings file.

A hook declared in SKILL.md runs only in the main conversation; a live check showed it does
not run for subagents, which do the skill's searching. Hooks from settings files run in
subagents too, so the installer adds the guard there as well (R21, KTD9).

Usage:
    python3 settings_hook.py add --skill-dir DIR [--settings FILE]
    python3 settings_hook.py remove [--settings FILE]
    python3 settings_hook.py status --skill-dir DIR [--settings FILE]

FILE defaults to ~/.claude/settings.json. The guard's entry is the PreToolUse hook whose
command carries the marker below, with the guard's own matcher (bin/guard_hook.py MATCHER); add
replaces it (a reinstall into another folder, or an older matcher) and keeps every other
setting and hook. The command is the one install.sh writes into the installed SKILL.md, so
Claude Code runs the guard once per call, not twice, while /hotel is active. Before changing an
existing file, add and remove copy it to FILE.bak-hotel-<time>. A file that is not valid JSON is
left untouched (exit 1).
status prints ok, missing, other_skill_dir or old_matcher (registered for this folder with an
older matcher; add updates it).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

MARKER = "hotel-skill-guard"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"


class SettingsFileError(Exception):
    """The settings file is not a JSON object; it is left untouched."""


def matcher() -> str:
    """The guard's matcher, from guard_hook itself (one list of the tools it acts on).

    Imported here, not at the top, so remove works and preflight can report a missing hook file.
    """
    from guard_hook import MATCHER
    return MATCHER


def command(skill_dir: Path) -> str:
    """The hook command: lets calls through when the hook file is gone (preflight then stops the run)."""
    hook = f"{Path(skill_dir)}/bin/guard_hook.py"
    return f'[ -f "{hook}" ] || exit 0; exec python3 "{hook}"  # {MARKER}'


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise SettingsFileError(f"{path} is not valid JSON; it was left untouched.") from None
    if not isinstance(data, dict):
        raise SettingsFileError(f"{path} does not hold a JSON object; it was left untouched.")
    return data


def _without_guard(groups: list) -> list:
    kept = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if MARKER not in str(h.get("command", ""))]
        if hooks:
            kept.append(dict(group, hooks=hooks))
    return kept


def _write(path: Path, data: dict) -> None:
    if path.is_file():
        shutil.copy2(path, path.with_name(f"{path.name}.bak-hotel-{time.strftime('%Y%m%d-%H%M%S')}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def add(path: Path, skill_dir: Path) -> str:
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    entry = {"matcher": matcher(), "hooks": [{"type": "command", "command": command(skill_dir), "timeout": 10}]}
    groups = hooks.get("PreToolUse", [])
    if entry in groups and len(_without_guard(groups)) == len(groups) - 1:
        return "already registered"
    hooks["PreToolUse"] = _without_guard(groups) + [entry]
    _write(path, data)
    return f"registered in {path}"


def remove(path: Path) -> str:
    data = _load(path)
    groups = data.get("hooks", {}).get("PreToolUse", [])
    kept = _without_guard(groups)
    if kept == groups:
        return "not registered"
    if kept:
        data["hooks"]["PreToolUse"] = kept
    else:
        del data["hooks"]["PreToolUse"]
    _write(path, data)
    return f"removed from {path}"


def status(path: Path, skill_dir: Path) -> str:
    try:
        groups = _load(path).get("hooks", {}).get("PreToolUse", [])
    except SettingsFileError:
        return "missing"
    ours = [(g.get("matcher"), str(h.get("command", ""))) for g in groups for h in g.get("hooks", [])
            if MARKER in str(h.get("command", ""))]
    if not ours:
        return "missing"
    mine = command(skill_dir)
    if (matcher(), mine) in ours:
        return "ok"
    return "old_matcher" if any(c == mine for _, c in ours) else "other_skill_dir"


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="The /hotel guard hook in a Claude Code settings file")
    parser.add_argument("action", choices=("add", "remove", "status"))
    parser.add_argument("--skill-dir")
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    args = parser.parse_args(argv[1:])
    path = Path(args.settings).expanduser()
    if args.action in ("add", "status") and not args.skill_dir:
        parser.error(f"{args.action} needs --skill-dir")
    try:
        if args.action == "add":
            print(add(path, Path(args.skill_dir).expanduser().resolve()))
        elif args.action == "remove":
            print(remove(path))
        else:
            print(status(path, Path(args.skill_dir).expanduser().resolve()))
    except SettingsFileError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
