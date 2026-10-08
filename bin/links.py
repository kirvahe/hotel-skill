#!/usr/bin/env python3
"""Build the links the user opens: Booking, Google Maps and Airbnb (R16, R19, R21).

Usage:
    python3 links.py RUN_DIR

Links only; nothing is fetched. Booking links carry the trip dates, the adults,
one room and EUR, so the user sees their own Genius price in their browser. A
Booking hotel URL from the research (booking_url) is used when it is a
booking.com/hotel/ page; otherwise the link is a Booking search for the name and
city. The Airbnb link is a search prefilled with the dates and adults, plus pets
only when the dog travels.

Prints {candidate id: {"name", "booking", "maps"[, "airbnb"]}} as JSON for the
merged candidates; special formats get the Airbnb link.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse, urlunparse

import runfiles


def booking_link(name: str, city: str, check_in: str, check_out: str, adults: int, booking_url: str = "") -> str:
    params = {"checkin": check_in, "checkout": check_out, "group_adults": adults,
              "no_rooms": 1, "selected_currency": "EUR"}
    parsed = urlparse(booking_url or "")
    host = parsed.netloc.lower()
    if (parsed.scheme in ("http", "https") and (host == "booking.com" or host.endswith(".booking.com"))
            and parsed.path.startswith("/hotel/")):
        return urlunparse(("https", parsed.netloc, parsed.path, "", urlencode(params), ""))
    return "https://www.booking.com/searchresults.html?" + urlencode(dict({"ss": f"{name}, {city}"}, **params))


def maps_link(name: str, street: str, city: str) -> str:
    query = ", ".join(part for part in (name, street, city) if part)
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})


def airbnb_link(location: str, check_in: str, check_out: str, adults: int, pets: bool) -> str:
    params = {"checkin": check_in, "checkout": check_out, "adults": adults}
    if pets:
        params["pets"] = 1
    return f"https://www.airbnb.com/s/{quote(location, safe='')}/homes?" + urlencode(params)


def candidate_links(candidate: dict, trip: dict) -> dict:
    city = trip["city"]
    out = {
        "name": candidate["name"],
        "booking": booking_link(candidate["name"], city, trip["check_in"], trip["check_out"], trip["guests"],
                                candidate.get("booking_url", "")),
        "maps": maps_link(candidate["name"], candidate.get("street", ""), city),
    }
    if candidate.get("kind") == "special-format":
        location = f"{candidate['area']}, {city}" if candidate.get("area") else city
        out["airbnb"] = airbnb_link(location, trip["check_in"], trip["check_out"], trip["guests"], trip["dog"])
    return out


def main(argv: list) -> int:
    if len(argv) != 2:
        print("Usage: python3 links.py RUN_DIR", file=sys.stderr)
        return 2
    run_dir = Path(argv[1]).expanduser()
    trip = runfiles.load_trip(run_dir)
    out = {c["id"]: candidate_links(c, trip) for c in runfiles.load_merged(run_dir)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(runfiles.run_cli(main, sys.argv))
