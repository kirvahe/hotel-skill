"""Builds a throwaway find-hotel run folder from the synthetic "Testgrad" fixture.

Every hotel, city, rating and trip here is made up.

The fixture run (2 guests, 20-22 November 2026, budget up to 200 EUR, dog at home):
    Casa Velarta + Hotel Casa Velarta   merge; engine price 160; Booking search says full (AE1)
    Palacio Ñandú + Palacio Nandu       merge across accents; engine unreadable (AE3)
    El Patio Lunar                      Booking only, 9.1 (AE4)
    Hotel Sombra                        scores 8.4 and 8.9 disagree; "no rooms" for other dates
    Hotel Invierno                      closed from the night of 21 November (AE2)
    Hotel Otoño                         closed from 22 November, after check-out
    Hotel Torre Alta                    engine price 290, above the budget (AE11)
    Hotel Marquesa Vieja                stayed twice before; engine price for other dates
    Hostería Gris                       verified 7.6, below the floor (AE9)
    Hotel Ceniza                        on the Testgrad blacklist
    Grandchain Testgrad Centro          named "do not recommend" chain
    Apartamentos Lirio                  apartment, an excluded kind
    Carmen del Aljibe Rojo              special format, Airbnb block (AE7)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = HERE.parent.parent.parent / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def make_run(tmp) -> Path:
    """Copy the fixture run into tmp and add blacklist.json and stays.json from the real parsers."""
    run = Path(tmp) / "run"
    shutil.copytree(HERE / "run", run)
    for script, arg, out in (("blacklist.py", HERE / "blacklist-feedback", "blacklist.json"),
                             ("stays.py", HERE / "stays-history.md", "stays.json")):
        result = subprocess.run([sys.executable, str(BIN / script), str(arg)],
                                capture_output=True, text=True, check=True)
        (run / out).write_text(result.stdout, encoding="utf-8")
    return run


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def edit_candidate(run: Path, family: str, name: str, **changes) -> None:
    """Change fields of one candidate record in candidates-{family}.jsonl (None deletes a field)."""
    path = run / f"candidates-{family}.jsonl"
    records = read_jsonl(path)
    hits = [r for r in records if r["name"] == name]
    assert hits, f"{name} not in {path.name}"
    for record in hits:
        for key, value in changes.items():
            if value is None:
                record.pop(key, None)
            else:
                record[key] = value
    write_jsonl(path, records)


def score(value: str) -> dict:
    return {"value": value, "reviews": 10, "source_url": "https://search.example/q?x", "quote": f"Rated {value}"}


def pet(value: str) -> dict:
    return {"value": value, "source_url": "https://pets.example/policy", "quote": f"Dogs: {value}"}


def pipeline(run: Path) -> None:
    """Run merge, fit filter and status table on the run folder."""
    import fit_filter
    import merge_candidates
    import status_table
    merge_candidates.merge_run(run)
    fit_filter.filter_run(run)
    status_table.status_run(run)
