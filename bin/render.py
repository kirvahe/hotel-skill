#!/usr/bin/env python3
"""Render the shortlist and the final answer from the run ledger, in one fixed layout.

Usage:
    python3 render.py shortlist RUN_DIR [--lang ru]   the checkpoint list (R14), plain-reply path
    python3 render.py options RUN_DIR [--lang ru]     the same entries as question-tool options (JSON)
    python3 render.py answer RUN_DIR [--lang ru]      the final answer (R17, R25, R19, R16 links)

Reads trip.json, merged.jsonl, fit.json, status.json, and when present
verdicts.json (the model's R25 "clearly beats the in-budget options" calls:
{"clearly_better": [{"candidate": "Name", "reason": "one line"}]}),
checkpoints.json (strike-outs from apply_reply.py), research.json (negative
reports from the research envelopes), context.json (earlier strike-outs from the
city cache), families.json and modules.json (the R22 report), and, for the
answer only, advice.json (the model's overview, "why you" and vibe lines,
district advice and tips) and final.json (the final check's room, rate and
cancellation terms).

Groups:
    hotels         kept by the fit filter, not unavailable, not struck out, and either
                   without an engine price or priced within the budget
    beyond budget  priced above the budget AND named in verdicts.json; any other
                   over-budget candidate is not shown at all (R25, AE11)
    airbnb         special formats, always "dates not verified" (R19)
    skipped        a "Skipped: {reason} — {hotel} — {detail}" line for each fit-filter
                   removal and each unavailable hotel
    checks         every research family and optional module: ran / partial / skipped /
                   failed, with the reason (R22)

Entry numbers are stable for the whole run: a candidate keeps its number in every
render, in the options and in the answer (numbers.json), so a reply's numbers
always mean the same hotels. When no hotel survives, the hotels section becomes
"Nothing fits" with what removed the candidates and what to change (F2, R17).

Labels follow the request language (R20): ru and en; any other language falls
back to en with a visible note.

    python3 render.py questions RUN_DIR [--lang ru]   the checkpoint as question-tool questions (JSON)

"questions" splits the entries into at most 4 multi-select questions of 2 to 4
options (the question tool's limits); with 1 entry or more than 16 it returns
{"mode": "plain"} and the shortlist is answered as a plain reply.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
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
        "price_unclear": "{price} — per night or for the whole stay ❓",
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
        "reason_judgment": "fails a profile rule",
        "flag_pet_restricted": "dogs allowed with conditions ❓",
        "flag_pet_room_unconfirmed": "dogs allowed, room type not confirmed ❓",
        "flag_pet_room_not_allowed": "no dogs in some room types ❓",
        "pet_quote": "Pet policy: “{quote}”",
        "negative_report": "⚠ Negative report: “{quote}”",
        "struck_before": "Struck out before ({date}): {reason}",
        "why_you": "Why you: {text}",
        "vibe": "Vibe: {text}",
        "room_rate": "Checked on the hotel's site: {text}",
        "cancellation": "Cancellation: {text}",
        "districts": "Where to stay",
        "tips": "Tips",
        "report": "Checks",
        "report_line": "{name}: {status}",
        "status_ran": "ran",
        "status_partial": "partial",
        "status_skipped": "skipped",
        "status_failed": "failed",
        "not_recorded": "no status recorded",
        "history_skipped": "history check skipped",
        "family_curated-press": "Curated lists and local press",
        "family_reddit": "Reddit",
        "family_booking-search": "Booking in search results",
        "module_gmail": "Booking history in Gmail",
        "module_resolver": "Hotel websites (closures, pet policy)",
        "module_reader": "Availability on hotels' own booking engines",
        "module_final_check": "Final price check",
        "cancel_free_until": "free until {date}",
        "cancel_unknown": "unknown ❓",
        "why_text": "{text}",
        "why_reader_missing": "background browser not installed",
        "why_nothing_to_read": "no hotel needed a read",
        "why_nothing_passed": "nothing passed the checks",
        "why_kept_nothing": "you kept nothing",
        "why_no_official_site": "no kept hotel has its own website",
        "why_no_candidates": "no hotel passed the filter",
        "why_missing_batch": "batch {batch} wrote no files",
        "why_no_batch": "no batch wrote its files",
        "why_invalid_lines": "{count} invalid line(s) left out",
        "why_reprompt_invalid": "{count} invalid line(s) left out after one re-prompt",
        "strike_header": "Strike out",
        "strike_question": "Strike out any of {first}–{last}? Under Other, add a reason, new dates, budget or dog answer.",
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
        "price_unclear": "{price} — за ночь или за весь срок ❓",
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
        "reason_judgment": "не проходит по профилю",
        "flag_pet_restricted": "с собакой — с условиями ❓",
        "flag_pet_room_unconfirmed": "с собакой можно, но для типа номера не подтверждено ❓",
        "flag_pet_room_not_allowed": "в некоторые типы номеров с собакой нельзя ❓",
        "pet_quote": "Правила для животных: «{quote}»",
        "negative_report": "⚠ Отрицательный отзыв: «{quote}»",
        "struck_before": "Уже вычеркивали ({date}): {reason}",
        "why_you": "Почему вам: {text}",
        "vibe": "Атмосфера: {text}",
        "room_rate": "Проверено на сайте отеля: {text}",
        "cancellation": "Отмена: {text}",
        "districts": "Где жить",
        "tips": "Советы",
        "report": "Проверки",
        "report_line": "{name}: {status}",
        "status_ran": "выполнено",
        "status_partial": "частично",
        "status_skipped": "пропущено",
        "status_failed": "не удалось",
        "not_recorded": "статус не записан",
        "history_skipped": "проверка истории пропущена",
        "family_curated-press": "Подборки и местная пресса",
        "family_reddit": "Reddit",
        "family_booking-search": "Booking в поисковой выдаче",
        "module_gmail": "История бронирований в Gmail",
        "module_resolver": "Сайты отелей (закрытия, правила для животных)",
        "module_reader": "Свободные номера на сайтах отелей",
        "module_final_check": "Финальная проверка цен",
        "cancel_free_until": "бесплатно до {date}",
        "cancel_unknown": "неизвестно ❓",
        "why_text": "{text}",
        "why_reader_missing": "фоновый браузер не установлен",
        "why_nothing_to_read": "проверять было нечего",
        "why_nothing_passed": "ни один вариант не прошёл проверки",
        "why_kept_nothing": "вы ничего не оставили",
        "why_no_official_site": "ни у одного из оставленных отелей нет своего сайта",
        "why_no_candidates": "ни один отель не прошёл фильтр",
        "why_missing_batch": "группа {batch}: агент не записал файлы",
        "why_no_batch": "ни одна группа не записала файлы",
        "why_invalid_lines": "отброшено строк с ошибками: {count}",
        "why_reprompt_invalid": "после повторного запроса отброшено строк с ошибками: {count}",
        "strike_header": "Вычеркнуть",
        "strike_question": "Вычеркнуть что-то из {first}–{last}? В поле «Другое» можно указать причину, новые даты, бюджет или ответ про собаку.",
    },
}
FALLBACK_NOTE = "Note: labels in '{lang}' are not available yet; showing English labels."
PET_FLAGS = ("pet_unknown", "pet_restricted", "pet_room_unconfirmed", "pet_room_not_allowed")
FLAG_ORDER = ("booking_only", "score_unverified") + PET_FLAGS + ("below_floor",)
QUOTED_PET_FLAGS = ("pet_restricted", "pet_room_not_allowed")
REMOVAL_ORDER = ("below_floor", "blacklist", "dnr_chain", "judgment", "excluded_kind", "pet_not_allowed",
                 "unavailable", "over_budget", "struck")
SKIP_LINE_CODES = ("below_floor", "blacklist", "dnr_chain", "judgment", "excluded_kind", "pet_not_allowed",
                   "unavailable")
DISTRICT_CODES = ("below_floor", "blacklist", "dnr_chain", "judgment", "excluded_kind", "pet_not_allowed")
FAMILIES = ("curated-press", "reddit", "booking-search")
QUESTIONS_MAX, OPTIONS_MIN, OPTIONS_MAX = 4, 2, 4  # the question tool's limits


def labels_for(lang: str) -> tuple[dict, str]:
    code = (lang or "en").lower().replace("_", "-").split("-")[0]
    if code in LABELS:
        return LABELS[code], ""
    return LABELS["en"], FALLBACK_NOTE.format(lang=lang)


def money(amount, labels: dict) -> str:
    return labels["price"].format(amount=f"{amount:g}")


def nightly(price, basis: str, nights: int):
    """The price judged against a nightly budget. An unclear price may be the stay total,
    so it is judged by the lowest nightly price it allows."""
    if price is None:
        return None
    return price / nights if basis == "unknown" else price


def _by_name(merged_candidate: dict, records: list, key: str = "candidate") -> list:
    keys = runfiles.record_keys(merged_candidate)
    return [r for r in records if runfiles.name_key(r.get(key, "")) in keys]


def build_view(run_dir: Path) -> dict:
    """Sort every merged candidate into hotels / beyond / airbnb / removed and number the shown ones."""
    run_dir = Path(run_dir)
    trip = runfiles.load_trip(run_dir)
    merged = runfiles.load_merged(run_dir)
    fit = runfiles.load_json(run_dir, "fit.json", "run fit_filter.py first")
    status = runfiles.load_json(run_dir, "status.json", "run status_table.py first")["candidates"]
    verdicts = runfiles.optional_json(run_dir, "verdicts.json", {"clearly_better": []})
    struck = runfiles.active_strikes(runfiles.read_checkpoints(run_dir))
    negative = runfiles.optional_json(run_dir, runfiles.RESEARCH, {}).get("negative_reports") or []
    struck_before = ((runfiles.optional_json(run_dir, runfiles.CONTEXT, {}).get("cache") or {}).get("struck_out") or [])
    advice = runfiles.optional_json(run_dir, runfiles.ADVICE, {})
    final = runfiles.optional_json(run_dir, runfiles.FINAL, {}).get("final") or []
    fit_by_id = {c["id"]: c for c in fit["candidates"]}
    budget = trip["budget"]["max"]
    nights = (date.fromisoformat(trip["check_out"]) - date.fromisoformat(trip["check_in"])).days

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
        own_advice = _by_name(candidate, advice.get("entries") or [])
        own_final = _by_name(candidate, final)
        entry = {
            "id": cid, "name": name, "area": candidate.get("area", ""), "block": verdict["block"],
            "price": price, "price_basis": state.get("price_basis") or "per_night", "flags": [f for f in FLAG_ORDER if f in verdict["flags"]],
            "past_stays": verdict.get("past_stays", []), "scarcity": state.get("scarcity"), "why": "",
            "pet_quote": (verdict.get("pet") or {}).get("quote", ""),
            "negative": [r.get("quote", "") for r in _by_name(candidate, negative) if r.get("quote")],
            "struck_before": [r for r in struck_before if runfiles.name_key(r.get("name", "")) in runfiles.record_keys(candidate)],
            "advice": own_advice[-1] if own_advice else {},
            "final": own_final[-1] if own_final else {},
            "links": links.candidate_links(candidate, trip),
        }
        if verdict["block"] == "airbnb":
            entry["flags"] = [f for f in entry["flags"] if f == "booking_only" or f in PET_FLAGS]
            entry["price"] = None
            airbnb.append(entry)
            continue
        if state["status"] == "unavailable":
            removed.append({"code": "unavailable", "name": name, "detail": state.get("quote", "")})
            continue
        per_night = nightly(price, entry["price_basis"], nights)
        if per_night is not None and per_night > budget:
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
            "airbnb": airbnb, "removed": removed, "advice": advice,
            "families": runfiles.optional_json(run_dir, runfiles.FAMILIES, {}).get("families") or {},
            "modules": runfiles.optional_json(run_dir, runfiles.MODULES, {}).get("modules") or {}}


def _floor(view: dict) -> str:
    return str(float(view["rules"]["floor"]))


def _reason_label(code: str, view: dict, labels: dict) -> str:
    return labels[f"reason_{code}"].format(floor=_floor(view))


def _status_text(entry: dict, labels: dict) -> str:
    if entry["block"] == "airbnb":
        return labels["dates_not_verified"]
    if entry["price"] is not None:
        key = "price_unclear" if entry["price_basis"] == "unknown" else "per_night"
        return labels[key].format(price=money(entry["price"], labels))
    return labels["availability_unknown"]


def _flag_texts(entry: dict, view: dict, labels: dict) -> list:
    return [labels[f"flag_{flag}"].format(floor=_floor(view)) for flag in entry["flags"]]


def _entry_lines(entry: dict, view: dict, labels: dict, with_links: bool) -> list:
    head = [f"{entry['number']}. **{entry['name']}**"] + ([entry["area"]] if entry["area"] else [])
    lines = [" — ".join(head + [_status_text(entry, labels)])]
    flags = _flag_texts(entry, view, labels)
    if flags:
        lines.append("   " + " · ".join(flags))
    if entry["pet_quote"] and any(f in entry["flags"] for f in QUOTED_PET_FLAGS):
        lines.append("   " + labels["pet_quote"].format(quote=entry["pet_quote"]))
    if with_links:
        for key, label in (("why", "why_you"), ("vibe", "vibe")):
            if entry["advice"].get(key):
                lines.append("   " + labels[label].format(text=entry["advice"][key]))
        details = " · ".join(entry["final"][k] for k in ("room_type", "rate") if entry["final"].get(k))
        if details:
            lines.append("   " + labels["room_rate"].format(text=details))
        cancellation = entry["final"].get("cancellation") or {}
        if cancellation.get("deadline"):
            text = labels["cancel_free_until"].format(date=cancellation["deadline"])
        elif cancellation.get("value") == "unknown":
            text = labels["cancel_unknown"]
        else:
            text = cancellation.get("value", "")
        if text:
            lines.append("   " + labels["cancellation"].format(text=text))
    for quote in entry["negative"]:
        lines.append("   " + labels["negative_report"].format(quote=quote))
    for earlier in entry["struck_before"]:
        lines.append("   " + labels["struck_before"].format(date=earlier.get("date", ""), reason=earlier.get("reason", "")).rstrip(": "))
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


def why_text(why: list, labels: dict) -> str:
    """Reasons the scripts record as codes, in the label language; unknown codes print as given."""
    texts = []
    for item in why:
        template = labels.get(f"why_{item.get('code')}")
        try:
            texts.append(template.format(**item) if template else str(item.get("text") or item.get("code", "")))
        except KeyError:
            texts.append(str(item.get("code", "")))
    return "; ".join(t for t in texts if t)


def _status_line(name: str, record, labels: dict, history: bool = False) -> str:
    if not record or record.get("status") not in runfiles.STATUSES:
        return "- " + labels["report_line"].format(name=name, status=labels["not_recorded"])
    reason = why_text(record["why"], labels) if record.get("why") else (record.get("reason") or "")
    if record["status"] == "ran":
        reason = ""
    if history and record["status"] == "skipped":
        reason = labels["history_skipped"] + (f": {reason}" if reason else "")
    line = labels["report_line"].format(name=name, status=labels[f"status_{record['status']}"])
    return "- " + line + (f" — {reason}" if reason else "")


def _report(view: dict, labels: dict) -> list:
    lines = [f"### {labels['report']}"]
    lines += [_status_line(labels[f"family_{f}"], view["families"].get(f), labels) for f in FAMILIES]
    lines += [_status_line(labels[f"module_{m}"], view["modules"].get(m), labels, history=m == "gmail")
              for m in runfiles.MODULES_ORDER]
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
    if with_links and view["advice"].get("overview"):
        out += ["", view["advice"]["overview"]]
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
    if with_links:
        for key in ("districts", "tips"):
            items = [item for item in view["advice"].get(key) or [] if item]
            if items:
                out += [f"### {labels[key]}"] + [f"- {item}" for item in items] + [""]
    skipped = [item for item in view["removed"] if item["code"] in SKIP_LINE_CODES]
    if skipped:
        out.append(f"### {labels['skipped']}")
        out += ["- " + labels["skipped_line"].format(reason=_reason_label(item["code"], view, labels),
                                                     name=item["name"], detail=item["detail"]).rstrip(" —")
                for item in skipped]
        out.append("")
    out += _report(view, labels) + [""]
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


def chunk_sizes(count: int) -> list:
    """Option counts per question, or [] when the entries do not fit the question tool."""
    if count < OPTIONS_MIN or count > QUESTIONS_MAX * OPTIONS_MAX:
        return []
    questions = -(-count // OPTIONS_MAX)
    base, extra = divmod(count, questions)
    return [base + 1] * extra + [base] * (questions - extra)


def question_payload(run_dir: Path, lang: str = "en") -> dict:
    """The checkpoint for the question tool: the shortlist text, then multi-select strike-out questions."""
    labels, _ = labels_for(lang)
    text = render_shortlist(run_dir, lang)
    options = question_options(run_dir, lang)
    sizes = chunk_sizes(len(options))
    if not sizes:
        return {"mode": "plain", "text": text, "questions": []}
    questions, start = [], 0
    for size in sizes:
        part = options[start:start + size]
        start += size
        questions.append({
            "question": labels["strike_question"].format(first=part[0]["number"], last=part[-1]["number"]),
            "header": labels["strike_header"][:12], "multiSelect": True,
            "options": [{"label": o["label"], "description": o["description"]} for o in part]})
    return {"mode": "question", "text": text, "questions": questions}


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="render the find-hotel shortlist or answer")
    parser.add_argument("mode", choices=("shortlist", "options", "questions", "answer"))
    parser.add_argument("run_dir")
    parser.add_argument("--lang", default="en")
    args = parser.parse_args(argv[1:])
    run_dir = Path(args.run_dir).expanduser()
    if args.mode == "options":
        print(json.dumps(question_options(run_dir, args.lang), ensure_ascii=False, indent=2))
    elif args.mode == "questions":
        print(json.dumps(question_payload(run_dir, args.lang), ensure_ascii=False, indent=2))
    elif args.mode == "shortlist":
        print(render_shortlist(run_dir, args.lang), end="")
    else:
        print(render_answer(run_dir, args.lang), end="")
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
