#!/usr/bin/env python3
"""Read a hotel's own booking engine for the trip dates, in a browser with no visible window.

The reader opens the hotel's official site or booking-engine URL in headless Chromium
(Playwright for Python), reads the visible text and appends one evidence record in the run
ledger format (bin/ledger.py): engine_price, engine_no_rooms or engine_unreadable. Each record
carries a quote of the visible text, read_at, source_url and, for engine evidence, dates_shown:
the check-in and check-out dates the page itself shows, with their quote.

It signs into nothing and never types, clicks or submits, so it always stops before any
personal-data or payment step (R13). It refuses every Booking or Airbnb page, whether as the
start URL, as a link on the hotel's site or as a redirect, and records unknown (R21).

Usage:
    python3 engine_reader.py --candidate NAME --url URL --check-in YYYY-MM-DD
        --check-out YYYY-MM-DD --guests N --out EVIDENCE.jsonl
        --page-timeout-s SECONDS --give-up-after-s SECONDS [--fixture SAVED.html]

--url may hold {check_in}, {check_out} and {guests} placeholders, which take the trip values;
a date placeholder accepts a strftime format, e.g. {check_in:%d/%m/%Y}. That is how a caller
sets the dates on an engine that takes them in its URL.
--page-timeout-s   the longest wait for one page to load and settle.
--give-up-after-s  the per-engine give-up rule: total time for every page of one read (redirect
                   checks, the hotel's site, its booking link). When it runs out the reader
                   records engine_unreadable.
Both limits are required and have no defaults: the user approves the values after the live smoke.
--fixture reads a saved HTML file as the page at --url. It never imports Playwright and makes
no request.

What a page yields (phrases in the PATTERNS table below):
    a price in EUR and dates shown              -> engine_price (see "The price" below)
    a no-availability statement and dates shown -> engine_no_rooms
    both on one page, either without readable dates, or neither -> engine_unreadable
A calendar legend such as "× = No availability" is not a no-availability statement.

The price. price_eur is per night when price_basis is "per_night": the lowest of the lines that
say per night ("175 € × 2 nights" for the trip's number of nights, "160 € per night") or give a
total for the trip's nights ("Total for 2 nights: 351 €", "Total: 351 €"), the total divided by
the nights. Lines for another number of nights (a longer-stay offer), tax and savings lines and
other sites' prices ("Booking.com: 428 €", or the label on the line before the amount) never
count. When no line says per night or total, price_eur is the lowest amount left and price_basis
is "unknown": it may be the price per night or for the whole stay.
When the start page gives no engine evidence, the reader follows the first booking link on it
that is not Booking or Airbnb, once, and that page decides.

Exit codes:
    0  a record was written (any kind)
    1  the record failed ledger validation and was not written (a bug)
    2  bad arguments
    3  refused under R21; an engine_unreadable record was written
    4  skipped: Playwright or its browser is not installed (R22); nothing was written
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import ENGINE_KINDS, validate_evidence  # noqa: E402

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_REFUSED, EXIT_SKIPPED = 0, 1, 2, 3, 4
SKIP_MESSAGE = "SKIPPED: background browser not installed"
NO_TEXT = "[no page text]"

# The phrase table. Each pattern is a regular expression searched in one line of visible text
# after folding: lowercase, accents removed ("disponibilità" -> "disponibilita"), curly
# apostrophes made straight. Write patterns in that folded form. To add a language, add its
# key to each group.
PATTERNS = {
    # Page-level statements that no room is left for the dates. Room-level words such as
    # "sold out" or "agotada" stay out: they sit next to other rooms that are still for sale.
    "no_rooms": {
        "es": [r"no hay disponibilidad", r"sin disponibilidad", r"no tenemos disponibilidad",
               r"no (?:hay|quedan|tenemos) habitaciones disponibles", r"no quedan habitaciones"],
        "it": [r"nessuna disponibilita", r"non c'e disponibilita", r"nessuna camera disponibile",
               r"non (?:ci sono|vi sono|abbiamo) camere disponibili"],
        "fr": [r"aucune disponibilite", r"pas de disponibilite", r"aucune chambre (?:n'est )?disponible",
               r"complet (?:pour|a|aux) (?:ces|les|vos) dates"],
        "en": [r"no availability", r"no rooms? (?:are |is )?available", r"fully booked",
               r"not available (?:for|on) (?:the|your|these|those) (?:selected )?dates"],
    },
    # Per-night wording next to an amount, without a number of nights.
    "per_night": {
        "es": [r"(?:\bpor|/)\s?noche\b"],
        "it": [r"(?:\ba|\bper|/)\s?notte\b"],
        "fr": [r"(?:\bpar|/)\s?nuit\b"],
        "en": [r"(?:\bper|\ba|/)\s?night\b"],
    },
    # The word for night(s), after a number: "x 2 nights" is per night, "2 nights" alone a total.
    "nights": {
        "es": [r"noches?"],
        "it": [r"notti", r"notte"],
        "fr": [r"nuits?"],
        "en": [r"nights?"],
    },
    # A total, which without a number of nights is for the dates searched.
    "total": {
        "es": [r"\btotal\b"],
        "it": [r"\btotale\b"],
        "fr": [r"\btotal\b"],
        "en": [r"\btotal\b"],
    },
    # Lines whose EUR amount is not a room price: tourist taxes and savings.
    "not_a_room_price": {
        "es": [r"tasa turistica", r"impuesto turistico", r"\bahorra"],
        "it": [r"tassa di soggiorno", r"imposta di soggiorno", r"\brisparmi"],
        "fr": [r"taxe de sejour", r"\beconomise"],
        "en": [r"\b(?:city|tourist|resort) tax\b", r"\bsave\b"],
    },
    # Link text of a booking link on the hotel's own site.
    "booking_link": {
        "es": [r"\breserv", r"disponibilidad"],
        "it": [r"\bprenot", r"disponibilita"],
        "fr": [r"\breserv", r"disponibilite"],
        "en": [r"\bbook", r"\breserv", r"availability"],
    },
}

# Month names and abbreviations, folded. Day-first dates ("20 nov 2026", "20 de noviembre")
# use all of them; month-first dates ("Nov 20, 2026") only the English ones, so the Spanish
# "mar 20 nov" (martes) is not read as 20 March.
MONTHS = {
    1: ["enero", "ene", "gennaio", "gen", "janvier", "janv", "january", "jan"],
    2: ["febrero", "feb", "febbraio", "fevrier", "fevr", "fev", "february"],
    3: ["marzo", "mar", "mars", "march"],
    4: ["abril", "abr", "aprile", "apr", "avril", "avr", "april"],
    5: ["mayo", "may", "maggio", "mag", "mai"],
    6: ["junio", "jun", "giugno", "giu", "juin", "june"],
    7: ["julio", "jul", "luglio", "lug", "juillet", "juil", "july"],
    8: ["agosto", "ago", "aout", "august", "aug"],
    9: ["septiembre", "setiembre", "settembre", "septembre", "september", "sept", "sep", "set"],
    10: ["octubre", "ottobre", "octobre", "october", "oct", "ott"],
    11: ["noviembre", "novembre", "november", "nov"],
    12: ["diciembre", "dicembre", "decembre", "december", "dic", "dec"],
}
ENGLISH_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
                  "september", "october", "november", "december",
                  "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov", "dec")


def _compile(group: str) -> list:
    return [re.compile(p) for patterns in PATTERNS[group].values() for p in patterns]


NO_ROOMS = _compile("no_rooms")
NOT_A_ROOM_PRICE = _compile("not_a_room_price")
BOOKING_LINK = _compile("booking_link")
PER_NIGHT = _compile("per_night")
TOTAL = _compile("total")
NIGHTS_WORD = "(?:" + "|".join(p for patterns in PATTERNS["nights"].values() for p in patterns) + r")\b"
# "× 2 nights": the amount before the sign is per night. A letter x counts only on its own ("max 2").
TIMES_NIGHTS = re.compile(r"(?<![a-z])[×x*]\s?(\d{1,2})\s?" + NIGHTS_WORD)
N_NIGHTS = re.compile(r"\b(\d{1,2})\s?" + NIGHTS_WORD)
# Calendar legends: one or two symbols, then "=" and the meaning ("× = No availability").
LEGEND = re.compile(r"^\s*\S{1,2}\s*=\s*")
# Other sites' prices, shown by some engines to prove theirs is lower. Folded, like the patterns.
OTHER_SITES = re.compile(r"\b(?:booking\.com|expedia|hotels\.com|agoda|trivago|kayak|priceline|trip\.com)\b")
MONTH_NUMBER = {name: number for number, names in MONTHS.items() for name in names}


def _alternation(names) -> str:
    return "|".join(sorted(names, key=len, reverse=True))


# Thousands separators: "." "," and the no-break spaces French prices use; decimals: "." or ",".
_AMOUNT = r"(\d{1,3}(?:[.,\u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
PRICES = [re.compile(r"(?:€|\beur\b)\s?" + _AMOUNT), re.compile(_AMOUNT + r"\s?(?:€|\beuros?\b|\beur\b)")]
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")  # day first
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th|er|º|°)?\.?\s+(?:de\s+)?(" + _alternation(MONTH_NUMBER)
                       + r")\b\.?(?:,?\s+(?:de\s+)?(\d{4})\b)?")
MONTH_DAY = re.compile(r"\b(" + _alternation(ENGLISH_MONTHS) + r")\b\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4})\b)?")


@dataclass
class Trip:
    check_in: date
    check_out: date
    guests: int


@dataclass
class Page:
    """What one load returned: the final URL, visible text lines and (absolute href, text) links."""
    url: str
    lines: list = field(default_factory=list)
    links: list = field(default_factory=list)


class PageError(Exception):
    """The page could not be read: timeout, network error, block."""


class Refused(Exception):
    """A Booking or Airbnb URL came up (start, link or redirect hop) and was not loaded."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


class _GaveUp(Exception):
    pass


def fold(text: str) -> str:
    """Lowercase, accents removed, straight apostrophes. No-break spaces stay (they separate thousands)."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace("\u2019", "'")


def refused_host(url: str) -> str | None:
    """The host when the URL is a Booking or Airbnb page (R21), else None."""
    host = (urlsplit(url).hostname or "").rstrip(".")
    if host == "booking.com" or host.endswith(".booking.com") or "airbnb" in host.split("."):
        return host
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evidence(candidate: str, kind: str, source_url: str, quote: str, **fields) -> dict:
    record = {"candidate": candidate, "kind": kind, "source_url": source_url, "quote": quote, "read_at": _now()}
    record.update({key: value for key, value in fields.items() if value is not None})
    return record


def unreadable(candidate: str, source_url: str, quote: str, reason: str) -> dict:
    return evidence(candidate, "engine_unreadable", source_url, quote, reason=reason)


def refusal(candidate: str, source_url: str, refused_url: str, quote: str) -> dict:
    reason = (f"refused: {refused_url} is a Booking or Airbnb page, and the reader never opens "
              "Booking or Airbnb (R21)")
    return unreadable(candidate, source_url, quote, reason)


# ---------------------------------------------------------------- reading a page's text

def parse_amount(text: str) -> float:
    text = text.replace("\u00a0", "").replace("\u202f", "")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in text or "." in text:
        parts = text.split("," if "," in text else ".")
        thousands = len(parts) > 2 or len(parts[-1]) == 3
        text = "".join(parts) if thousands else ".".join(parts)
    return float(text)


def _amounts(folded: str) -> list:
    """(amount, end position) of every non-zero EUR amount on a folded line."""
    found = []
    for pattern in PRICES:
        for match in pattern.finditer(folded):
            amount = parse_amount(match.group(1))
            if amount > 0:
                found.append((amount, match.end()))
    return found


def _line_price(folded: str, nights: int) -> tuple | None:
    """(per-night amount, "per_night") or (amount, "unknown") for one line, or None when it does not count."""
    amounts = _amounts(folded)
    if not amounts:
        return None
    times = TIMES_NIGHTS.search(folded)
    if times:
        if int(times[1]) != nights:
            return None  # an offer for another number of nights
        before = [amount for amount, end in amounts if end <= times.start()]
        return (before[-1] if before else min(a for a, _ in amounts)), "per_night"
    lowest = min(amount for amount, _ in amounts)
    if any(p.search(folded) for p in PER_NIGHT):
        return lowest, "per_night"
    count = N_NIGHTS.search(folded)
    if count:
        return (lowest / nights, "per_night") if int(count[1]) == nights else None
    if any(p.search(folded) for p in TOTAL):
        return lowest / nights, "per_night"
    return lowest, "unknown"


def room_price(lines: list, trip: Trip) -> tuple | None:
    """(amount, line, price_basis): the lowest per-night price, else the lowest amount of unknown basis.

    Lowest, because understating a price keeps a hotel in the budget for the user to check,
    while overstating it would push the hotel out to the beyond-budget group (R25).
    """
    nights = (trip.check_out - trip.check_in).days
    best = {"per_night": None, "unknown": None}
    after_other_site = False
    for line in lines:
        folded = fold(line)
        label_only = bool(OTHER_SITES.search(folded)) and not _amounts(folded)
        skip = after_other_site or OTHER_SITES.search(folded) or any(p.search(folded) for p in NOT_A_ROOM_PRICE)
        after_other_site = label_only
        if skip:
            continue
        found = _line_price(folded, nights)
        if found and (best[found[1]] is None or found[0] < best[found[1]][0]):
            best[found[1]] = (found[0], line)
    for basis in ("per_night", "unknown"):
        if best[basis]:
            return round(best[basis][0], 2), best[basis][1], basis
    return None


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _dated(day: int, month: int, year: int | None, trip: Trip) -> date | None:
    """A date; a page date without a year takes the year that puts it nearest the trip."""
    if year:
        return _date(year, month, day)
    options = [_date(y, month, day) for y in (trip.check_in.year - 1, trip.check_in.year, trip.check_in.year + 1)]
    options = [d for d in options if d]
    return min(options, key=lambda d: abs((d - trip.check_in).days)) if options else None


def _dates_in(line: str, trip: Trip) -> list:
    folded = fold(line)
    found, spans = [], []
    for match in ISO_DATE.finditer(folded):
        found.append((match.start(), _date(int(match[1]), int(match[2]), int(match[3]))))
        spans.append(match.span())
    for match in NUMERIC_DATE.finditer(folded):
        found.append((match.start(), _date(int(match[3]), int(match[2]), int(match[1]))))
        spans.append(match.span())
    for match in DAY_MONTH.finditer(folded):
        year = int(match[3]) if match[3] else None
        found.append((match.start(), _dated(int(match[1]), MONTH_NUMBER[match[2]], year, trip)))
        spans.append(match.span())
    for match in MONTH_DAY.finditer(folded):
        if any(match.start() < end and start < match.end() for start, end in spans):
            continue
        year = int(match[3]) if match[3] else None
        found.append((match.start(), _dated(int(match[2]), MONTH_NUMBER[match[1]], year, trip)))
    return [day for _, day in sorted(found, key=lambda item: item[0]) if day]


def dates_shown(lines: list, trip: Trip) -> dict | None:
    """The check-in and check-out dates the page shows, with the lines they came from.

    When both trip dates appear, those are the dates shown. Otherwise the first two different
    dates on the page are, earlier first. None when the page shows fewer than two dates.
    """
    first_line = {}
    for line in lines:
        for day in _dates_in(line, trip):
            first_line.setdefault(day, line)
    if trip.check_in in first_line and trip.check_out in first_line:
        check_in, check_out = trip.check_in, trip.check_out
    elif len(first_line) >= 2:
        check_in, check_out = sorted(list(first_line)[:2])
    else:
        return None
    quote_lines = list(dict.fromkeys([first_line[check_in], first_line[check_out]]))
    return {"check_in": check_in.isoformat(), "check_out": check_out.isoformat(), "quote": " / ".join(quote_lines)}


def classify(candidate: str, page: Page, trip: Trip) -> dict:
    """One evidence record for one page. A page that cannot settle the question is unreadable (R12)."""
    price = room_price(page.lines, trip)
    no_rooms = next((line for line in page.lines
                     if not LEGEND.match(line) and any(p.search(fold(line)) for p in NO_ROOMS)), None)
    if price and no_rooms:
        return unreadable(candidate, page.url, f"{price[1]} / {no_rooms}",
                          "the page shows both a price and a no-availability statement")
    shown = dates_shown(page.lines, trip)
    if price and shown:
        return evidence(candidate, "engine_price", page.url, price[1], price_eur=price[0], price_basis=price[2],
                        dates_shown=shown)
    if no_rooms and shown:
        return evidence(candidate, "engine_no_rooms", page.url, no_rooms, dates_shown=shown)
    if price or no_rooms:
        return unreadable(candidate, page.url, price[1] if price else no_rooms,
                          "the page shows a price or a no-availability statement but no check-in and check-out dates")
    return unreadable(candidate, page.url, page.lines[0] if page.lines else NO_TEXT,
                      "the page shows neither a price in EUR nor a no-availability statement")


def booking_link(page: Page) -> tuple:
    """(first booking link that is not Booking or Airbnb, [(href, text) of refused booking links])."""
    here = page.url.split("#")[0]
    refused = []
    for href, text in page.links:
        if urlsplit(href).scheme not in ("http", "https") or href.split("#")[0] == here:
            continue
        if not any(p.search(fold(text)) for p in BOOKING_LINK):
            continue
        if refused_host(href):
            refused.append((href, text))
            continue
        return href, refused
    return None, refused


# ---------------------------------------------------------------- one engine read

def read_engine(candidate: str, url: str, trip: Trip, fetch, *, page_timeout_s: float,
                give_up_after_s: float, clock=time.monotonic) -> tuple:
    """(evidence record, refused under R21). fetch(url, timeout_s) returns a Page.

    Loads the start URL; when it gives no engine evidence, follows its first booking link that
    is not Booking or Airbnb, once. Every load counts against the give-up rule.
    """
    if refused_host(url):
        return refusal(candidate, url, url, NO_TEXT), True
    deadline = clock() + give_up_after_s
    target = url

    def load(target_url: str) -> Page:
        remaining = deadline - clock()
        if remaining <= 0:
            raise _GaveUp()
        return fetch(target_url, min(page_timeout_s, remaining))

    try:
        page = load(target)
        record = classify(candidate, page, trip)
        if record["kind"] in ENGINE_KINDS:
            return record, False
        link, refused_links = booking_link(page)
        if link is None and refused_links:
            href, text = refused_links[0]
            return refusal(candidate, page.url, href, text), True
        if link is None:
            return record, False
        target = link
        return classify(candidate, load(target), trip), False
    except Refused as error:
        return refusal(candidate, target, error.url, NO_TEXT), True
    except _GaveUp:
        return unreadable(candidate, target, NO_TEXT,
                          f"gave up: the per-engine give-up rule ({give_up_after_s:g} s) ran out before {target} was read"), False
    except PageError as error:
        return unreadable(candidate, target, NO_TEXT, str(error)), False


def resolve_redirects(url: str, probe) -> str:
    """Follow HTTP redirects one hop at a time without loading a Booking or Airbnb hop.

    probe(url) returns (status, Location header or None) without following the redirect.
    A browser route handler sees only the first URL of a redirect chain, so the chain is
    checked here, before the browser navigates.
    """
    seen = set()
    while True:
        if refused_host(url):
            raise Refused(url)
        if url in seen:
            raise PageError(f"redirect loop at {url}")
        seen.add(url)
        status, location = probe(url)
        if not (300 <= status < 400 and location):
            return url
        url = urljoin(url, location)


# ---------------------------------------------------------------- fixture mode

_SPACES = re.compile(r"[ \t\r\n\f\v]+")  # not no-break spaces: they separate thousands in prices


def clean_lines(raw_lines) -> list:
    lines = (_SPACES.sub(" ", line).strip() for line in raw_lines)
    return [line for line in lines if line]


class _VisibleText(HTMLParser):
    """Text and links of saved HTML, as near to what a browser shows as a parser without CSS gets.

    Leaves out script, style, title and template content, elements with the hidden attribute or
    an inline display:none / visibility:hidden style, and hidden inputs. Text hidden by a
    stylesheet class is not detected here; the browser path reads innerText, which leaves it out.
    """
    SKIP = {"script", "style", "noscript", "template", "title"}
    BLOCK = {"address", "article", "aside", "blockquote", "br", "button", "caption", "dd", "div", "dl", "dt",
             "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
             "hr", "label", "legend", "li", "main", "nav", "ol", "option", "p", "pre", "section", "select",
             "table", "tbody", "tfoot", "thead", "tr", "ul"}
    CELL = {"td", "th"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    INPUTS_WITHOUT_TEXT = {"hidden", "checkbox", "radio"}

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.lines = [[]]
        self.links = []
        self.anchor = None
        self.skip_tag, self.skip_depth = None, 0

    def _newline(self):
        if self.lines[-1]:
            self.lines.append([])

    def handle_starttag(self, tag, attrs):
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        attrs = dict(attrs)
        style = re.sub(r"\s+", "", (attrs.get("style") or "").lower())
        if tag in self.SKIP or "hidden" in attrs or "display:none" in style or "visibility:hidden" in style:
            if tag not in self.VOID:
                self.skip_tag, self.skip_depth = tag, 1
            return
        if tag == "input":
            if (attrs.get("type") or "text").lower() not in self.INPUTS_WITHOUT_TEXT and attrs.get("value"):
                self._newline()
                self.lines[-1].append(attrs["value"])
                self._newline()
            return
        if tag in self.BLOCK:
            self._newline()
        elif tag in self.CELL:
            self.lines[-1].append(" ")
        if tag == "a" and attrs.get("href"):
            self.anchor = (urljoin(self.base_url, attrs["href"]), [], attrs.get("aria-label") or attrs.get("title") or "")

    def handle_endtag(self, tag):
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if tag in self.BLOCK:
            self._newline()
        if tag == "a" and self.anchor:
            href, parts, label = self.anchor
            self.links.append((href, " ".join("".join(parts).split()) or label))
            self.anchor = None

    def handle_data(self, data):
        if self.skip_tag:
            return
        self.lines[-1].append(data)
        if self.anchor:
            self.anchor[1].append(data)


def page_from_html(html: str, url: str) -> Page:
    parser = _VisibleText(url)
    parser.feed(html)
    parser.close()
    return Page(url=url, lines=clean_lines("".join(parts) for parts in parser.lines), links=parser.links)


def fixture_fetcher(start_url: str, html_file: Path):
    def fetch(url: str, timeout_s: float) -> Page:
        if url != start_url:
            raise PageError(f"fixture mode reads only the saved page for --url; no saved page for {url}")
        return page_from_html(html_file.read_text(encoding="utf-8"), url)
    return fetch


# ---------------------------------------------------------------- browser mode

_VISIBLE_INPUT_VALUES = ("els => els.filter(e => e.value && e.checkVisibility({visibilityProperty: true}))"
                         ".map(e => e.value)")
_LINKS = "els => els.map(a => [a.href, (a.innerText || a.getAttribute('aria-label') || a.title || '').trim()])"


def _first_line(error: Exception) -> str:
    return (str(error).strip().splitlines() or [type(error).__name__])[0]


def _guard(route):
    """Context-wide route: no request to a Booking or Airbnb host leaves the browser (R21)."""
    if refused_host(route.request.url):
        route.abort("blockedbyclient")
    else:
        route.continue_()


class BrowserFetcher:
    """Loads one page at a time in a headless Chromium context with no stored login."""

    def __init__(self, context, playwright_error):
        self.context = context
        self.error = playwright_error

    def _probe(self, url: str, timeout_ms: float) -> tuple:
        try:
            response = self.context.request.get(url, max_redirects=0, timeout=timeout_ms)
        except self.error as error:
            raise PageError(f"could not check {url} for redirects: {_first_line(error)}") from None
        try:
            return response.status, response.headers.get("location")
        finally:
            response.dispose()

    def __call__(self, url: str, timeout_s: float) -> Page:
        deadline = time.monotonic() + timeout_s

        def left_ms() -> float:
            ms = (deadline - time.monotonic()) * 1000
            if ms < 1:  # Playwright reads a timeout of 0 as "wait forever"
                raise PageError(f"page timeout: {url} did not load within the page timeout")
            return ms

        if urlsplit(url).scheme in ("http", "https"):
            url = resolve_redirects(url, lambda hop: self._probe(hop, left_ms()))
        page = self.context.new_page()
        try:
            page.set_default_timeout(left_ms())
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=left_ms())
            except self.error as error:
                raise PageError(f"page did not load: {_first_line(error)}") from None
            try:
                page.wait_for_load_state("networkidle", timeout=left_ms())
            except (self.error, PageError):
                pass  # read whatever has rendered when the page timeout runs out
            hops = [page.url]
            request = response.request if response else None
            while request:
                hops.append(request.url)
                request = request.redirected_from
            for hop in hops:
                if refused_host(hop):
                    raise Refused(hop)
            lines = []
            for frame in page.frames:  # booking engines are often iframes on the hotel's site
                if refused_host(frame.url):
                    continue
                try:
                    lines += frame.inner_text("body").splitlines()  # innerText leaves out CSS-hidden text
                except self.error:
                    continue
            try:
                lines += page.eval_on_selector_all(
                    "input:not([type=hidden]):not([type=checkbox]):not([type=radio])", _VISIBLE_INPUT_VALUES)
                links = page.eval_on_selector_all("a[href]", _LINKS)
            except self.error as error:
                raise PageError(f"could not read the page: {_first_line(error)}") from None
            return Page(url=page.url, lines=clean_lines(lines), links=[(href, text) for href, text in links])
        finally:
            page.close()


def read_in_browser(candidate: str, url: str, trip: Trip, limits: dict) -> tuple | None:
    """read_engine in headless Chromium; None when the browser is not installed (R22)."""
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        print(SKIP_MESSAGE)
        return None
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as error:
            print(f"{SKIP_MESSAGE} or could not start: {_first_line(error)}")
            return None
        try:
            # en-GB: day-first dates and English month names, which the date patterns read.
            context = browser.new_context(locale="en-GB", accept_downloads=False, service_workers="block")
            context.route("**/*", _guard)
            return read_engine(candidate, url, trip, BrowserFetcher(context, PlaywrightError), **limits)
        finally:
            browser.close()


# ---------------------------------------------------------------- command line

def fill_url(url: str, trip: Trip) -> str:
    if "{" not in url:
        return url
    return url.format(check_in=trip.check_in, check_out=trip.check_out, guests=trip.guests)


def _iso_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a YYYY-MM-DD date") from None


def _positive(kind):
    def convert(text: str):
        try:
            value = kind(text)
        except ValueError:
            value = 0
        if value <= 0:
            raise argparse.ArgumentTypeError(f"{text!r} must be a number above 0")
        return value
    return convert


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Read a hotel's own booking engine in a headless browser.")
    parser.add_argument("--candidate", required=True, help="hotel name as in the candidate record")
    parser.add_argument("--url", required=True, help="official site or booking-engine URL")
    parser.add_argument("--check-in", required=True, type=_iso_date)
    parser.add_argument("--check-out", required=True, type=_iso_date)
    parser.add_argument("--guests", required=True, type=_positive(int))
    parser.add_argument("--out", required=True, help="evidence .jsonl file; one record is appended")
    parser.add_argument("--page-timeout-s", required=True, type=_positive(float),
                        help="longest wait for one page (user-approved value)")
    parser.add_argument("--give-up-after-s", required=True, type=_positive(float),
                        help="per-engine give-up rule: total seconds for one read (user-approved value)")
    parser.add_argument("--fixture", type=Path, help="saved HTML file to read instead of opening a browser")
    args = parser.parse_args(argv[1:])
    if args.check_out <= args.check_in:
        parser.error("--check-out must be after --check-in")
    trip = Trip(args.check_in, args.check_out, args.guests)
    try:
        url = fill_url(args.url, trip)
    except (KeyError, IndexError, ValueError) as error:
        parser.error(f"--url placeholders are {{check_in}}, {{check_out}} and {{guests}}; got {error}")
    if urlsplit(url).scheme not in ("http", "https", "file"):
        parser.error("--url must start with http://, https:// or file://")
    if args.fixture and not args.fixture.is_file():
        parser.error(f"--fixture {args.fixture} is not a file")
    limits = {"page_timeout_s": args.page_timeout_s, "give_up_after_s": args.give_up_after_s}

    if refused_host(url):
        result = (refusal(args.candidate, url, url, NO_TEXT), True)
    elif args.fixture:
        result = read_engine(args.candidate, url, trip, fixture_fetcher(url, args.fixture), **limits)
    else:
        result = read_in_browser(args.candidate, url, trip, limits)
        if result is None:
            return EXIT_SKIPPED
    record, refused = result

    problems = validate_evidence(record)
    if problems:
        print("engine_reader: record not written, it fails the ledger format: " + "; ".join(problems), file=sys.stderr)
        return EXIT_INVALID
    with open(args.out, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False))
    if refused:
        print(f"REFUSED: {record['reason']}", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
