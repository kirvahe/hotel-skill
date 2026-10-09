#!/usr/bin/env python3
"""Read and update a city cache: DATA/cities/{city-slug}.md (R3, R15).

Usage:
    python3 citycache.py read CACHE_FILE      prints the cache as JSON

The cache is the city's memory across trips. orchestrate.py reads it at stage 2
(source map slices for the research agents, earlier strike-outs, exclusions) and
writes it after the checkpoint and the answer. Sections it reads and writes:

    ## Searched                one line per run: "- {date} {trip}: {summary}"
    ## Sources                 table Family | Outlet | Kind | Language | Where | Yield | Last used
                               (Where is a URL, or the query for a Booking search)
    ## Recommended             table Name | Type | Area | Rating | Notes
    ## Struck out              table Name | Reason | Date | Trip (the user's reason, verbatim)
    ## Excluded (with reason)  read only: "- {hotel} — {reason}" lines are hard exclusions

Every other section (Mentioned, archived rounds, criteria changes, notes) and every
HTML comment is kept as it is. Rows merge by key, so writing twice for one run
changes nothing: Sources by family and Where, Recommended by hotel name,
Struck out by hotel name and trip, Searched by trip.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import runfiles

SEARCHED, SOURCES, RECOMMENDED, STRUCK, EXCLUDED = (
    "Searched", "Sources", "Recommended", "Struck out", "Excluded (with reason)")
CANONICAL = (SEARCHED, SOURCES, RECOMMENDED, STRUCK, EXCLUDED)
COLUMNS = {
    SOURCES: ("Family", "Outlet", "Kind", "Language", "Where", "Yield", "Last used"),
    RECOMMENDED: ("Name", "Type", "Area", "Rating", "Notes"),
    STRUCK: ("Name", "Reason", "Date", "Trip"),
}
FAMILIES = ("curated-press", "reddit", "booking-search")
UPDATED = re.compile(r"^(\*?)Updated: (?:\d{4}-\d{2}-\d{2}|YYYY-MM-DD)(\*?)\s*$")


def _key(table: str, row: dict) -> tuple:
    if table == SOURCES:
        return (row.get("family", "").lower(), row.get("where", "").strip().lower())
    if table == STRUCK:
        return (runfiles.name_key(row.get("name", "")), row.get("trip", ""))
    return (runfiles.name_key(row.get("name", "")),)


def _cell(value) -> str:
    return " ".join(str("" if value is None else value).replace("|", "/").split())


def _split(text: str) -> tuple[list, list]:
    """(lines before the first section, [[title, body lines], ...])."""
    head, sections = [], []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append([line[3:].strip(), []])
        elif sections:
            sections[-1][1].append(line)
        else:
            head.append(line)
    return head, sections


def _visible(body: list) -> list:
    """Indexes of body lines outside HTML comments."""
    out, inside = [], False
    for i, line in enumerate(body):
        stripped = line.strip()
        if inside:
            inside = "-->" not in stripped
            continue
        if stripped.startswith("<!--"):
            inside = "-->" not in stripped
            continue
        out.append(i)
    return out


def _cells(line: str) -> list:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table(body: list):
    """(start, end, rows) of the first table outside comments, or None. Rows are dicts by lowercase header."""
    visible = _visible(body)
    for n, i in enumerate(visible):
        if not body[i].lstrip().startswith("|") or i + 1 >= len(body):
            continue
        if not re.fullmatch(r"\|?\s*:?-{3,}.*", body[i + 1].strip()):
            continue
        header = [c.lower() for c in _cells(body[i])]
        end, rows = i + 2, []
        while end < len(body) and body[end].lstrip().startswith("|"):
            cells = _cells(body[end])
            if any(cells):
                rows.append(dict(zip(header, cells)))
            end += 1
        return i, end, rows
    return None


def _bullets(body: list) -> list:
    return [body[i].strip()[2:].strip() for i in _visible(body) if body[i].strip().startswith("- ")]


def _section(sections: list, title: str):
    return next((s for s in sections if s[0] == title), None)


def parse(text: str) -> dict:
    _, sections = _split(text)

    def rows(title: str) -> list:
        section = _section(sections, title)
        found = _table(section[1]) if section else None
        return found[2] if found else []

    excluded = []
    section = _section(sections, EXCLUDED)
    if section:
        for item in _bullets(section[1]):
            name, _, reason = item.partition(" — ")
            excluded.append({"name": name.strip(), "reason": reason.strip()})
        for row in rows(EXCLUDED):
            name = row.get("name") or row.get("hotel") or ""
            if name:
                excluded.append({"name": name, "reason": row.get("reason", "")})
    return {"sources": rows(SOURCES), "recommended": [r for r in rows(RECOMMENDED) if r.get("name")],
            "struck_out": [r for r in rows(STRUCK) if r.get("name")], "excluded": excluded}


def read(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {"exists": False, "path": str(path), "sources": [], "recommended": [], "struck_out": [], "excluded": []}
    return dict(parse(path.read_text(encoding="utf-8")), exists=True, path=str(path))


def slices(sources: list) -> dict:
    """The cached source map per research family, as the briefs' {source_map_slice} takes it."""
    out = {family: [] for family in FAMILIES}
    for row in sources:
        family = row.get("family", "")
        if family not in out:
            continue
        item = {"outlet": row.get("outlet", ""), "kind": row.get("kind", ""), "language": row.get("language", "")}
        item["query" if row.get("kind") == "booking-query" else "url"] = row.get("where", "")
        out[family].append(item)
    return out


def _table_lines(title: str, rows: list) -> list:
    columns = COLUMNS[title]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_cell(row.get(c.lower(), "")) for c in columns) + " |" for row in rows]
    return lines


def _tidy(body: list) -> list:
    """One blank line after the heading, no runs of blank lines, one blank line at the end."""
    out = []
    for line in body:
        if line.strip() or (out and out[-1].strip()):
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return [""] + out + [""]


def _insert_at_end(body: list, block: list) -> list:
    """Insert block after the section's last content line (not a blank line, rule or comment).

    A bullet added after a bullet joins the list; anything else is set off by a blank line.
    """
    visible = _visible(body)
    content = [i for i in visible if body[i].strip() and body[i].strip() != "---"]
    if content:
        at = content[-1] + 1
        joined = block[0].startswith("- ") and body[content[-1]].strip().startswith("- ")
    else:
        hidden = [i for i in range(len(body)) if i not in visible]
        at, joined = (hidden[-1] + 1 if hidden else 0), False
    return _tidy(body[:at] + ([] if joined else [""]) + block + [""] + body[at:])


def _merge_rows(title: str, old: list, new: list) -> list:
    rows = [dict(r) for r in old]
    index = {_key(title, r): i for i, r in enumerate(rows)}
    for row in new:
        row = {k.lower(): _cell(v) for k, v in row.items()}
        key = _key(title, row)
        if key in index:
            rows[index[key]] = row
        else:
            index[key] = len(rows)
            rows.append(row)
    return rows


def _set_table(body: list, title: str, new: list) -> list:
    found = _table(body)
    if found:
        start, end, old = found
        return _tidy(body[:start] + _table_lines(title, _merge_rows(title, old, new)) + body[end:])
    return _insert_at_end(body, _table_lines(title, _merge_rows(title, [], new)))


def _set_searched(body: list, run_id: str, line: str) -> list:
    marker = f" {run_id}:"
    visible = set(_visible(body))
    body = [b for i, b in enumerate(body) if not (i in visible and marker in b)]
    return _insert_at_end(body, [f"- {line}"])


def update(text, *, city: str, today: str, run_id: str, searched: str, sources: list,
           recommended: list, struck: list) -> str:
    """The cache text after one run: new sections are created, managed sections merged, others kept."""
    if not text or not text.strip():
        head, sections = [f"# {city}", "", f"Updated: {today}", ""], [[title, [""]] for title in CANONICAL]
    else:
        head, sections = _split(text)
        if any(UPDATED.match(line) for line in head):
            head = [UPDATED.sub(lambda m: f"{m.group(1)}Updated: {today}{m.group(2)}", line) for line in head]
        else:
            head = head[:1] + ["", f"Updated: {today}"] + head[1:]
        for n, title in enumerate(CANONICAL):
            if _section(sections, title):
                continue
            before = [i for i, s in enumerate(sections) if s[0] in CANONICAL[:n]]
            sections.insert(before[-1] + 1 if before else 0, [title, [""]])
    for section in sections:
        title, body = section
        if title == SEARCHED:
            section[1] = _set_searched(body, run_id, searched)
        elif title == SOURCES:
            section[1] = _set_table(body, SOURCES, [dict(s, **{"last used": today}) for s in sources])
        elif title == RECOMMENDED:
            section[1] = _set_table(body, RECOMMENDED, recommended)
        elif title == STRUCK:
            section[1] = _set_table(body, STRUCK, struck)
    lines = list(head)
    for title, body in sections:
        lines += [f"## {title}"] + body
    return "\n".join(lines).rstrip() + "\n"


def write(path: Path, **changes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    path.write_text(update(old, **changes), encoding="utf-8")
    return path


def main(argv: list) -> int:
    if len(argv) != 3 or argv[1] != "read":
        print("Usage: python3 citycache.py read CACHE_FILE", file=sys.stderr)
        return 2
    print(json.dumps(read(Path(argv[2]).expanduser()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
