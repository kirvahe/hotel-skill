#!/usr/bin/env python3
"""Render the shortlist and the final answer from the run ledger, in one fixed layout.

Usage:
    python3 render.py shortlist RUN_DIR [--lang ru]   the checkpoint list (R14), plain-reply path
    python3 render.py options RUN_DIR [--lang ru]     the same entries as question-tool options (JSON)
    python3 render.py answer RUN_DIR [--lang ru]      the final answer (R17, R25, R19, R16 links)

Reads trip.json, merged.jsonl, fit.json, status.json, and when present
verdicts.json (the model's R25 "clearly beats the in-budget options" calls:
{"clearly_better": [{"candidate": "Name", "reason": "one line"}]}) and
checkpoints.json (strike-outs from apply_reply.py).

Groups:
    hotels         kept by the fit filter, not unavailable, not struck out, and either
                   without an engine price or priced within the budget
    beyond budget  priced above the budget AND named in verdicts.json; any other
                   over-budget candidate is not shown at all (R25, AE11)
    airbnb         special formats, always "dates not verified" (R19)
    skipped        a "Skipped: {reason} — {hotel} — {detail}" line for each fit-filter
                   removal and each unavailable hotel

Entry numbers are stable for the whole run: a candidate keeps its number in every
render, in the options and in the answer (numbers.json), so a reply's numbers
always mean the same hotels. When no hotel survives, the hotels section becomes
"Nothing fits" with what removed the candidates and what to change (F2, R17).

Labels follow the request language (R20): ru and en; any other language falls
back to en with a visible note.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import links
import runfiles

LABELS = {
    "en": {
        "shortlist_title": "Shortlist — {city}, {check_in} → {check_out}",
        "answer_title": "{city} — {check_in} → {check_out}",
        "trip_line": "Guests: {guests} · budget up to {budget}/night · {dog}",
        "dog_yes": "with the dog",
        "dog_no": "without the dog",
        "hotels": "Hotels",
        "beyond_budget": "Beyond budget",
        "airbnb": "Airbnb — special formats",
        "skipped": "Skipped",
        "skipped_line": "Skipped: {reason} — {name} — {detail}",
        "price": "€{amount}",
        "per_night": "{price}/night",
        "availability_unknown": "❓ availability not confirmed",
        "flag_booking_only": "Booking only, unconfirmed",
        "flag_score_unverified": "score unverified ❓",
        "flag_pet_unknown": "pet policy unknown",
        "flag_below_floor": "below your {floor} floor",
        "dates_not_verified": "dates not verified",
        "scarcity": "⚠ low availability: “{quote}”",
        "past_stay": "Stayed before: {stays}",
        "beyond_reason": "Why it is worth more: {reason}",
        "reply_hint": "Reply with the numbers to strike out (a reason helps). "
                      "You can also change the dates, the budget or the dog answer.",
        "nothing_fits": "Nothing fits",
        "removed_line": "What removed the candidates: {reasons}",
        "relax_line": "What to change: {options}",
        "relax_budget": "a higher budget",
        "lowest_price": "the lowest price found was {price}",
        "relax_district": "another district",
        "relax_dates": "other dates",
        "reason_below_floor": "below the {floor} floor",
        "reason_blacklist": "blacklist",
        "reason_dnr_chain": "do-not-recommend chain",
        "reason_excluded_kind": "excluded property type",
        "reason_pet_not_allowed": "dogs not allowed",
        "reason_unavailable": "not available for the dates",
        "reason_over_budget": "over budget",
        "reason_struck": "struck out by you",
    },
    "ru": {
        "shortlist_title": "Варианты — {city}, {check_in} → {check_out}",
        "answer_title": "{city} — {check_in} → {check_out}",
        "trip_line": "Гостей: {guests} · бюджет до {budget} за ночь · {dog}",
        "dog_yes": "с собакой",
        "dog_no": "без собаки",
        "hotels": "Отели",
        "beyond_budget": "Дороже бюджета",
        "airbnb": "Airbnb — необычное жильё",
        "skipped": "Отсеяно",
        "skipped_line": "Отсеяно: {reason} — {name} — {detail}",
        "price": "{amount} €",
        "per_night": "{price} за ночь",
        "availability_unknown": "❓ нет данных о свободных номерах",
        "flag_booking_only": "только Booking, без подтверждения",
        "flag_score_unverified": "оценка на Booking не подтверждена ❓",
        "flag_pet_unknown": "неизвестно, пускают ли с собакой",
        "flag_below_floor": "ниже вашего порога {floor}",
        "dates_not_verified": "даты не проверены",
        "scarcity": "⚠ мало свободных номеров: «{quote}»",
        "past_stay": "Вы уже останавливались здесь: {stays}",
        "beyond_reason": "Почему стоит дороже: {reason}",
        "reply_hint": "Напишите номера, которые вычеркнуть (можно с причиной). "
                      "Можно также поменять даты, бюджет или ответ про собаку.",
        "nothing_fits": "Ничего не подходит",
        "removed_line": "Что отсеялось: {reasons}",
        "relax_line": "Что можно поменять: {options}",
        "relax_budget": "поднять бюджет",
        "lowest_price": "самая низкая найденная цена — {price}",
        "relax_district": "другой район",
        "relax_dates": "другие даты",
        "reason_below_floor": "оценка ниже {floor}",
        "reason_blacklist": "чёрный список",
        "reason_dnr_chain": "сеть из списка «не рекомендовать»",
        "reason_excluded_kind": "неподходящий тип жилья",
        "reason_pet_not_allowed": "не пускают с собакой",
        "reason_unavailable": "нет мест на эти даты",
        "reason_over_budget": "дороже бюджета",
        "reason_struck": "вычеркнуто вами",
    },
}
FALLBACK_NOTE = "Note: labels in '{lang}' are not available yet; showing English labels."
FLAG_ORDER = ("booking_only", "score_unverified", "pet_unknown", "below_floor")
REMOVAL_ORDER = ("below_floor", "blacklist", "dnr_chain", "excluded_kind", "pet_not_allowed",
                 "unavailable", "over_budget", "struck")
SKIP_LINE_CODES = ("below_floor", "blacklist", "dnr_chain", "excluded_kind", "pet_not_allowed", "unavailable")
DISTRICT_CODES = ("below_floor", "blacklist", "dnr_chain", "excluded_kind", "pet_not_allowed")


def labels_for(lang: str) -> tuple[dict, str]:
    code = (lang or "en").lower().replace("_", "-").split("-")[0]
    if code in LABELS:
        return LABELS[code], ""
    return LABELS["en"], FALLBACK_NOTE.format(lang=lang)


def money(amount, labels: dict) -> str:
    return labels["price"].format(amount=f"{amount:g}")


def build_view(run_dir: Path) -> dict:
    """Sort every merged candidate into hotels / beyond / airbnb / removed and number the shown ones."""
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    merged = runfiles.load_merged(run_dir)
    fit = runfiles.load_json(run_dir, "fit.json", "run fit_filter.py first")
    status = runfiles.load_json(run_dir, "status.json", "run status_table.py first")["candidates"]
    verdicts = runfiles.optional_json(run_dir, "verdicts.json", {"clearly_better": []})
    struck = runfiles.active_strikes(runfiles.read_checkpoints(run_dir))
    fit_by_id = {c["id"]: c for c in fit["candidates"]}
    budget = trip["budget"]["max"]

    hotels, beyond, airbnb, removed = [], [], [], []
    for candidate in merged:
        cid = candidate["id"]
        if cid not in fit_by_id:
            raise runfiles.RunError("fit.json is older than merged.jsonl: run fit_filter.py again")
        if cid not in status:
            raise runfiles.RunError("status.json is older than merged.jsonl: run status_table.py again")
        verdict = fit_by_id[cid]
        state = status[cid]
        name = candidate["name"]
        if verdict["decision"] == "remove":
            removed.append({"code": verdict["reason_code"], "name": name, "detail": verdict["reason"]})
            continue
        if cid in struck:
            removed.append({"code": "struck", "name": name, "detail": struck[cid].get("reason", "")})
            continue
        price = state.get("price_eur") if state["status"] == "available" else None
        entry = {
            "id": cid, "name": name, "area": candidate.get("area", ""), "block": verdict["block"],
            "price": price, "flags": [f for f in FLAG_ORDER if f in verdict["flags"]],
            "past_stays": verdict.get("past_stays", []), "scarcity": state.get("scarcity"), "why": "",
            "links": links.candidate_links(candidate, trip),
        }
        if verdict["block"] == "airbnb":
            entry["flags"] = [f for f in entry["flags"] if f in ("booking_only", "pet_unknown")]
            entry["price"] = None
            airbnb.append(entry)
            continue
        if state["status"] == "unavailable":
            removed.append({"code": "unavailable", "name": name, "detail": state.get("quote", "")})
            continue
        if price is not None and price > budget:
            reason = next((v.get("reason", "") for v in verdicts.get("clearly_better", [])
                           if runfiles.name_key(v.get("candidate", "")) in runfiles.record_keys(candidate)), None)
            if reason is None:
                removed.append({"code": "over_budget", "name": name, "detail": "", "price": price})
            else:
                beyond.append(dict(entry, why=reason))
            continue
        hotels.append(entry)

    hotels.sort(key=lambda e: e["price"] is None)  # priced (available) first; stable otherwise
    numbers = runfiles.read_numbers(run_dir)
    changed = False
    for entry in hotels + beyond + airbnb:
        if entry["id"] not in numbers["numbers"]:
            numbers["numbers"][entry["id"]] = numbers["next"]
            numbers["next"] += 1
            changed = True
        entry["number"] = numbers["numbers"][entry["id"]]
    if changed:
        runfiles.write_json(run_dir / "numbers.json", numbers)
    for group in (hotels, beyond, airbnb):
        group.sort(key=lambda e: e["number"])
    return {"trip": trip, "rules": fit["rules"], "hotels": hotels, "beyond": beyond,
            "airbnb": airbnb, "removed": removed}


def _floor(view: dict) -> str:
    return str(float(view["rules"]["floor"]))


def _reason_label(code: str, view: dict, labels: dict) -> str:
    return labels[f"reason_{code}"].format(floor=_floor(view))


def _status_text(entry: dict, labels: dict) -> str:
    if entry["block"] == "airbnb":
        return labels["dates_not_verified"]
    if entry["price"] is not None:
        return labels["per_night"].format(price=money(entry["price"], labels))
    return labels["availability_unknown"]


def _flag_texts(entry: dict, view: dict, labels: dict) -> list:
    return [labels[f"flag_{flag}"].format(floor=_floor(view)) for flag in entry["flags"]]


def _entry_lines(entry: dict, view: dict, labels: dict, with_links: bool) -> list:
    head = [f"{entry['number']}. **{entry['name']}**"] + ([entry["area"]] if entry["area"] else [])
    lines = [" — ".join(head + [_status_text(entry, labels)])]
    flags = _flag_texts(entry, view, labels)
    if flags:
        lines.append("   " + " · ".join(flags))
    if entry["scarcity"]:
        lines.append("   " + labels["scarcity"].format(quote=entry["scarcity"]))
    if entry["past_stays"]:
        stays = "; ".join(f"{s.get('rating') or '—'} ({s.get('date', '')})" + (f" — {s['comment']}" if s.get("comment") else "")
                          for s in entry["past_stays"])
        lines.append("   " + labels["past_stay"].format(stays=stays))
    if entry["why"]:
        lines.append("   " + labels["beyond_reason"].format(reason=entry["why"]))
    if with_links:
        link = entry["links"]
        first = f"[Airbnb]({link['airbnb']})" if entry["block"] == "airbnb" else f"[Booking]({link['booking']})"
        lines.append(f"   {first} · [Google Maps]({link['maps']})")
    return lines


def _nothing_fits(view: dict, labels: dict) -> list:
    removed = view["removed"]
    counts = {}
    for item in removed:
        counts[item["code"]] = counts.get(item["code"], 0) + 1
    reasons = "; ".join(f"{_reason_label(code, view, labels)} — {counts[code]}"
                        for code in REMOVAL_ORDER if code in counts)
    codes = set(counts)
    options = []
    if codes & {"over_budget", "struck"}:
        prices = [item["price"] for item in removed if item["code"] == "over_budget"]
        budget = labels["relax_budget"]
        if prices:
            budget += f" ({labels['lowest_price'].format(price=money(min(prices), labels))})"
        options.append(budget)
    if codes & set(DISTRICT_CODES + ("struck",)) or not removed:
        options.append(labels["relax_district"])
    if codes & {"unavailable", "struck"}:
        options.append(labels["relax_dates"])
    lines = [f"### {labels['nothing_fits']}"]
    if reasons:
        lines.append(labels["removed_line"].format(reasons=reasons))
    lines.append(labels["relax_line"].format(options=" · ".join(options)))
    return lines


def _document(view: dict, lang: str, mode: str) -> str:
    labels, note = labels_for(lang)
    trip = view["trip"]
    with_links = mode == "answer"
    title = labels["shortlist_title" if mode == "shortlist" else "answer_title"].format(
        city=trip["city"], check_in=trip["check_in"], check_out=trip["check_out"])
    out = [f"## {title}", labels["trip_line"].format(
        guests=trip["guests"], budget=money(trip["budget"]["max"], labels),
        dog=labels["dog_yes" if trip["dog"] else "dog_no"])]
    if note:
        out.append(note)
    out.append("")
    if view["hotels"] or view["beyond"]:
        for key, group in (("hotels", view["hotels"]), ("beyond_budget", view["beyond"])):
            if group:
                out.append(f"### {labels[key]}")
                for entry in group:
                    out += _entry_lines(entry, view, labels, with_links)
                out.append("")
    else:
        out += _nothing_fits(view, labels) + [""]
    if view["airbnb"]:
        out.append(f"### {labels['airbnb']}")
        for entry in view["airbnb"]:
            out += _entry_lines(entry, view, labels, with_links)
        out.append("")
    skipped = [item for item in view["removed"] if item["code"] in SKIP_LINE_CODES]
    if skipped:
        out.append(f"### {labels['skipped']}")
        out += ["- " + labels["skipped_line"].format(reason=_reason_label(item["code"], view, labels),
                                                     name=item["name"], detail=item["detail"]).rstrip(" —")
                for item in skipped]
        out.append("")
    if mode == "shortlist":
        out.append(labels["reply_hint"])
    return "\n".join(out).rstrip() + "\n"


def render_shortlist(run_dir: Path, lang: str = "en") -> str:
    return _document(build_view(run_dir), lang, "shortlist")


def render_answer(run_dir: Path, lang: str = "en") -> str:
    return _document(build_view(run_dir), lang, "answer")


def question_options(run_dir: Path, lang: str = "en") -> list:
    """The shortlist entries as question-tool options, numbered like the plain list."""
    view = build_view(run_dir)
    labels, _ = labels_for(lang)
    return [{"number": e["number"], "label": f"{e['number']}. {e['name']}",
             "description": " · ".join([_status_text(e, labels)] + _flag_texts(e, view, labels))}
            for e in view["hotels"] + view["beyond"] + view["airbnb"]]


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="render the find-hotel shortlist or answer")
    parser.add_argument("mode", choices=("shortlist", "options", "answer"))
    parser.add_argument("run_dir")
    parser.add_argument("--lang", default="en")
    args = parser.parse_args(argv[1:])
    run_dir = Path(args.run_dir).expanduser()
    if args.mode == "options":
        print(json.dumps(question_options(run_dir, args.lang), ensure_ascii=False, indent=2))
    elif args.mode == "shortlist":
        print(render_shortlist(run_dir, args.lang), end="")
    else:
        print(render_answer(run_dir, args.lang), end="")
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
