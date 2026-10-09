"""Tests for bin/guard_hook.py: the PreToolUse hook that enforces R21 and KTD9.

Every hotel, URL and trip here is made up. Each test copies the hook into a temporary skill
folder whose data/ is a link to a temporary data folder, as in a real install, and runs it as
a subprocess with the hook JSON on stdin, the way Claude Code runs it. Nothing reaches the web.
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import engine_reader as reader  # noqa: E402
import guard_hook as guard  # noqa: E402

HOTEL_SITE = "https://hotel-inventado.example/reservas?entrada=2026-11-20&salida=2026-11-22"
BOOKING_PAGE = "https://www.booking.com/hotel/es/hotel-inventado.es.html?checkin=2026-11-20"
AIRBNB_PAGE = "https://www.airbnb.es/rooms/123456789"
GMAIL_SERVERS = ("mcp__gmail-personal__", "mcp__gmail-work__", "mcp__claude_ai_Gmail__", "mcp__plugin_mail_gmail__")
GMAIL_WRITES = ("send_message", "forward", "reply", "create_draft", "update_draft", "delete_draft",
                "label_thread", "label_message", "unlabel_thread", "create_label", "create_filter",
                "delete_filter", "modify_messages", "update_message_labels", "trash_thread",
                "trash_message", "mark_thread_spam", "create_event", "update_event")
GMAIL_READS = ("search_threads", "get_thread", "get_message", "list_labels", "list_drafts", "get_draft",
               "mailbox_info", "list_filters", "list_events", "get_event", "list_calendars")
SUBAGENT = {"agent_id": "agent-test-1", "agent_type": "general-purpose"}


class GuardTest(unittest.TestCase):
    """A temporary install: skill/bin/guard_hook.py and skill/data -> userdata/."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.skill = self.tmp / "skill"
        (self.skill / "bin").mkdir(parents=True)
        shutil.copy(BIN / "guard_hook.py", self.skill / "bin" / "guard_hook.py")
        self.data = self.tmp / "userdata"
        (self.data / "trips").mkdir(parents=True)
        (self.skill / "data").symlink_to(self.data)

    def open_run(self, stage="shortlist", trip="ciudad-inventada-2026-11"):
        run = self.data / "trips" / trip / "run"
        run.mkdir(parents=True, exist_ok=True)
        state = {"stage": stage, "waiting_for": [], "updated": "2026-10-09T10:00:00+00:00"}
        (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
        return run

    def hook(self, tool_name, tool_input, raw=None, **extra):
        payload = {
            "session_id": "test-session", "transcript_path": str(self.tmp / "transcript.jsonl"),
            "cwd": str(self.tmp), "permission_mode": "default", "hook_event_name": "PreToolUse",
            "tool_name": tool_name, "tool_input": tool_input, "tool_use_id": "toolu_test", **extra,
        }
        stdin = raw if raw is not None else json.dumps(payload)
        return subprocess.run([sys.executable, str(self.skill / "bin" / "guard_hook.py")],
                              input=stdin, capture_output=True, text=True, cwd=str(self.tmp))

    def assertBlocked(self, result, rule="R21"):
        self.assertEqual(result.returncode, 2, f"expected a block, got {result.returncode}: {result.stderr}")
        reason = result.stderr.strip()
        self.assertIn(rule, reason)
        self.assertEqual(len(reason.splitlines()), 1, reason)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertEqual(output["permissionDecisionReason"], reason)

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


class HostRuleTest(unittest.TestCase):
    def test_the_engine_reader_uses_the_guards_host_rule(self):
        self.assertIs(reader.refused_host, guard.refused_host)

    def test_host_rule(self):
        refused = [BOOKING_PAGE, AIRBNB_PAGE, "https://booking.com/", "https://secure.booking.com/x",
                   "https://www.airbnb.com/rooms/1", "https://es.airbnb.co.uk/s/x", "https://AIRBNB.IT/",
                   "https://www.booking.com./x"]
        allowed = [HOTEL_SITE, "https://notbooking.com/", "https://booking.com.hotel-inventado.example/",
                   "https://airbnb-fans.example/", "mailto:x@hotel-inventado.example"]
        for url in refused:
            with self.subTest(url=url):
                self.assertTrue(guard.refused_host(url))
        for url in allowed:
            with self.subTest(url=url):
                self.assertIsNone(guard.refused_host(url))


# The host regex the guard used before its linear host scan; the scan must find exactly what it found.
REGEX_HOST_IN_TEXT = re.compile(r"(?i)(?<![\w-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(?![\w-])")
HOST_TEXTS = ["curl -sL 'https://www.booking.com/x'", "site:booking.com hotel", "AIRBNB.es/rooms/1",
              "see www.boo\u212aing.com", "https%3A%2F%2Fwww.airbnb.com%2Frooms", "%2562ooking.com",
              "notbooking.com", "airbnb-fans.example", "booking.com.hotel-inventado.example", "git status",
              "grep -rn 'Booking' /tmp/run/", "hotel-inventado.example/reservas", "", "a." * 50 + "booking.com",
              "www.booking.com.x1", "a.b.c_d.booking.com", "-booking.com", "booking.com-", "booking.com.",
              "x." + "a" * 64 + ".booking.com", "a" * 64 + ".booking.com", "booking." + "c" * 64, "a..booking.com",
              "1.2.booking.com", "\u0130.booking.com", "booking.\u017fom", "airbnb.co.uk/x airbnb.es", "\u00e9.booking.com"]


def _full_scan(text):
    """refused_in_text as it was: the regex host scan on every form of the text, without the quick check."""
    for form in guard._forms(text):
        for host in REGEX_HOST_IN_TEXT.findall(form):
            if guard._refused(host.lower()):
                return host.lower()
    return None


def _random_texts(count, seed=20261009):
    """Short strings built from the pieces host names and their boundaries are made of."""
    pieces = ["booking", "airbnb", "com", "es", "co", "uk", "a", "b1", "x-y", "-", ".", ".", ".", "/", ":", " ",
              "_", "\u00e9", "\u212a", "\u0130", "\u0131", "\u017f", "9", "%2E", "c" * 62, "d" * 64]
    rng = random.Random(seed)
    return ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 14))) for _ in range(count)]


class HostInTextTest(unittest.TestCase):
    def test_quick_check_gives_the_full_scans_answer(self):
        for text in HOST_TEXTS:
            with self.subTest(text=text):
                self.assertEqual(guard.refused_in_text(text), _full_scan(text))

    def test_linear_host_scan_finds_what_the_regex_found(self):
        for text in HOST_TEXTS + _random_texts(4000):
            with self.subTest(text=text):
                self.assertEqual(list(guard.hosts_in_text(text)), REGEX_HOST_IN_TEXT.findall(text))
                self.assertEqual(guard.refused_in_text(text), _full_scan(text))

    def test_long_dotted_text_without_booking_or_airbnb_is_quick(self):
        text = "a." * 5000 + "-"  # 10 KB that sends the host scan into quadratic backtracking
        start = time.monotonic()
        self.assertIsNone(guard.refused_in_text(text))
        self.assertIsNone(guard.decide({"tool_name": "Bash", "tool_input": {"command": f"curl {text}"}}))
        self.assertLess(time.monotonic() - start, 0.2)

    def test_long_dotted_text_with_booking_is_quick(self):
        chain = "a." * 32000 + "-"  # 64 KB: the regex scan took over 40 s on this, past the hook's 10 s timeout
        for text in ("booking " + chain, chain + "booking", "https://hotel-inventado.example/?q=booking&x=" + chain):
            with self.subTest(text=text[:20]):
                start = time.monotonic()
                self.assertIsNone(guard.refused_in_text(text))
                self.assertIsNone(guard.decide({"tool_name": "Bash", "tool_input": {"command": f"curl {text}"}}))
                self.assertIsNone(guard.decide({"tool_name": "WebFetch", "tool_input": {"url": text}}))
                self.assertLess(time.monotonic() - start, 0.5)

    def test_url_with_many_embedded_schemes_is_quick_and_still_checked(self):
        many = "https://hotel-inventado.example/" + "http://a" * 16000  # 128 KB, 16000 embedded URLs
        start = time.monotonic()
        self.assertIsNone(guard.decide({"tool_name": "WebFetch", "tool_input": {"url": many + "booking"}}))
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(guard.refused_in_url(many + "https://www.booking.com/x"), "www.booking.com")
        self.assertEqual(guard.refused_in_url("https://proxy.example/https://user@www.booking.com/x"), "www.booking.com")
        self.assertEqual(guard.refused_in_url("https://proxy.example/http:/www.booking.com/x"), "www.booking.com")

    def test_importing_the_guard_loads_no_pathlib_or_datetime(self):
        code = ("import sys; before = set(sys.modules); sys.path.insert(0, sys.argv[1]); import guard_hook; "
                "print(sorted({'pathlib', 'datetime'} & (set(sys.modules) - before)))")
        result = subprocess.run([sys.executable, "-c", code, str(BIN)], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "[]"), result.stderr)


class MatcherTest(unittest.TestCase):
    """MATCHER starts the hook for every tool decide() acts on, and for no other MCP server."""
    OPEN_RUN = "/skill/data/trips/ciudad-inventada-2026-11/run"
    TRIGGER = {"url": BOOKING_PAGE, "command": f"curl '{BOOKING_PAGE}'"}

    def acts(self, tool):
        """decide() blocks this tool on input that every check refuses (a Gmail write with a run open)."""
        with mock.patch.object(guard, "open_run", return_value=self.OPEN_RUN):
            return guard.decide({"tool_name": tool, "tool_input": self.TRIGGER}) is not None

    def matches(self, tool):
        return re.search(guard.MATCHER, tool) is not None

    def test_server_names_need_no_escaping(self):
        for server in guard.BROWSER_SERVERS + guard.FETCH_SERVERS:
            self.assertRegex(server, r"^[A-Za-z0-9_-]+$")

    def test_every_tool_decide_acts_on_matches_directly_and_through_a_plugin(self):
        tools = ["Bash", "WebFetch"]
        for server in guard.BROWSER_SERVERS + guard.FETCH_SERVERS:
            tools += [f"mcp__{server}__browser_navigate", f"mcp__plugin_{server}_{server}__x",
                      f"mcp__plugin_some_plugin_{server}__x", f"mcp__plugin_{server}__x", f"mcp__{server}"]
        tools += [server + "send_message" for server in GMAIL_SERVERS]
        tools += ["mcp__GMAIL__x", "mcp__my-GMail-box__x", "mcp__plugin_mail_Gmail_work__reply"]
        for tool in tools:
            with self.subTest(tool=tool):
                self.assertTrue(self.acts(tool))
                self.assertTrue(self.matches(tool))

    def test_other_tools_do_not_match(self):
        tools = ["WebSearch", "Read", "Write", "Edit", "Agent", "mcp__claude_ai_Notion__notion-search",
                 "mcp__github__search_code", "mcp__claude_ai_Google_Drive__read_file_content",
                 "mcp__plugin_xfetch__x", "mcp__playwrightish__browser_navigate", "mcp__myexa__web_search_exa",
                 "mcp__icloud-calendar__create_event", "mcp__mail__send_message", "xmcp__playwright__x", "bash"]
        for tool in tools:
            with self.subTest(tool=tool):
                self.assertFalse(self.acts(tool))
                self.assertFalse(self.matches(tool))


class BrowserTest(GuardTest):
    def test_navigate_to_booking_is_blocked_with_a_reason(self):
        result = self.hook("mcp__playwright__browser_navigate", {"url": BOOKING_PAGE})
        self.assertBlocked(result)
        self.assertIn("www.booking.com", result.stderr)

    def test_navigate_to_the_hotels_own_site_passes(self):
        self.assertAllowed(self.hook("mcp__playwright__browser_navigate", {"url": HOTEL_SITE}))
        self.open_run()
        self.assertAllowed(self.hook("mcp__claude-in-chrome__navigate", {"url": HOTEL_SITE, "tabId": 7}))

    def test_booking_and_airbnb_are_blocked_on_every_browser_and_screen_server(self):
        cases = [
            ("mcp__claude-in-chrome__navigate", {"url": AIRBNB_PAGE, "tabId": 7}),
            ("mcp__claude-in-chrome__javascript_tool", {"action": "javascript_exec", "tabId": 7,
                                                        "text": "location.href = 'https://www.booking.com/'"}),
            ("mcp__playwright__browser_evaluate", {"function": "() => { window.location = 'https://airbnb.com/' }"}),
            ("mcp__computer-use__type", {"text": "booking.com\n"}),
            ("mcp__cmux-cua__type_text", {"text": "https://www.airbnb.it/rooms/42", "pid": 1}),
            ("mcp__plugin_playwright_playwright__browser_navigate", {"url": BOOKING_PAGE}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                self.assertBlocked(self.hook(tool, tool_input))

    def test_lookalike_hosts_pass(self):
        for url in ("https://notbooking.com/", "https://booking.com.hotel-inventado.example/"):
            with self.subTest(url=url):
                self.assertAllowed(self.hook("mcp__playwright__browser_navigate", {"url": url}))

    def test_call_without_a_url_is_blocked_only_while_a_run_is_open(self):
        cases = [
            ("mcp__claude-in-chrome__get_page_text", {"tabId": 7}),
            ("mcp__claude-in-chrome__navigate", {"url": "back", "tabId": 7}),
            ("mcp__playwright__browser_snapshot", {}),
            ("mcp__playwright__browser_click", {"element": "Reservar", "ref": "e12"}),
            ("mcp__computer-use__screenshot", {}),
            ("mcp__cmux-cua__get_window_state", {"pid": 1, "window_id": 2}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool, run="none"):
                self.assertAllowed(self.hook(tool, tool_input))
        self.open_run()
        for tool, tool_input in cases:
            with self.subTest(tool=tool, run="open"):
                self.assertBlocked(self.hook(tool, tool_input), rule="KTD9")


class FetchTest(GuardTest):
    def test_one_case_per_fetch_tool_family(self):
        cases = [
            ("WebFetch", {"url": BOOKING_PAGE, "prompt": "Quote the score"}),
            ("mcp__firecrawl__firecrawl_scrape", {"url": BOOKING_PAGE, "formats": ["markdown"]}),
            ("mcp__firecrawl__firecrawl_crawl", {"url": AIRBNB_PAGE, "limit": 5}),
            ("mcp__firecrawl__firecrawl_map", {"url": "booking.com"}),
            ("mcp__firecrawl__firecrawl_extract", {"urls": [HOTEL_SITE, BOOKING_PAGE], "prompt": "prices"}),
            ("mcp__firecrawl__firecrawl_interact", {"url": BOOKING_PAGE, "prompt": "read the price"}),
            ("mcp__firecrawl__firecrawl_parse", {"filePath": "/tmp/page.html", "url": AIRBNB_PAGE}),
            ("mcp__firecrawl__firecrawl_agent", {"prompt": "hotel prices", "urls": [BOOKING_PAGE]}),
            ("mcp__exa__web_fetch_exa", {"urls": [HOTEL_SITE, AIRBNB_PAGE]}),
            ("mcp__claude_ai_Exa__web_fetch_exa", {"urls": [BOOKING_PAGE]}),
            ("mcp__fetch__fetch", {"url": AIRBNB_PAGE}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                self.assertBlocked(self.hook(tool, tool_input))

    def test_fetching_the_hotels_own_site_passes(self):
        self.open_run()
        cases = [
            ("WebFetch", {"url": HOTEL_SITE, "prompt": "Quote the closure dates"}),
            ("mcp__firecrawl__firecrawl_scrape", {"url": HOTEL_SITE, "formats": ["markdown"]}),
            ("mcp__exa__web_fetch_exa", {"urls": [HOTEL_SITE]}),
            ("mcp__fetch__fetch", {"url": HOTEL_SITE}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                self.assertAllowed(self.hook(tool, tool_input))

    def test_booking_page_behind_a_proxy_or_encoded_is_blocked(self):
        for url in ("https://r.jina.example/https://www.booking.com/hotel/es/x.html",
                    "https://translate.example/?u=https%3A%2F%2Fwww.airbnb.com%2Frooms%2F1"):
            with self.subTest(url=url):
                self.assertBlocked(self.hook("WebFetch", {"url": url, "prompt": "x"}))

    def test_booking_host_without_a_scheme_inside_another_url_is_blocked(self):
        urls = ("https://translate.google.com/translate?sl=auto&tl=en&u=www.booking.com/hotel/es/x.html",
                "https://webcache.googleusercontent.com/search?q=cache:www.booking.com/hotel/es/x.html",
                "https://web.archive.org/web/2025/www.booking.com/hotel/es/x.html",
                "https://web.archive.org/web/2025/airbnb.es/rooms/1",
                "https://translate.example/?u=www.booking.com%2Fhotel%2Fes%2Fx.html")
        for url in urls:
            for tool in ("WebFetch", "mcp__firecrawl__firecrawl_scrape"):
                with self.subTest(url=url, tool=tool):
                    result = self.hook(tool, {"url": url})
                    self.assertBlocked(result)
                    self.assertRegex(result.stderr, r"would fetch (www\.booking\.com|airbnb\.es)\.")

    def test_hotel_url_that_only_mentions_booking_passes(self):
        urls = (HOTEL_SITE + "&utm_source=booking", "https://hotel-inventado.example/blog/booking-tips?ref=airbnb",
                "https://hotel-inventado.example/blog/booking.com-review")
        for url in urls:
            for tool in ("WebFetch", "mcp__firecrawl__firecrawl_scrape"):
                with self.subTest(url=url, tool=tool):
                    self.assertAllowed(self.hook(tool, {"url": url}))

    def test_browser_code_in_a_fetch_call_is_checked(self):
        self.assertBlocked(self.hook("mcp__firecrawl__firecrawl_interact", {
            "url": HOTEL_SITE, "code": "await page.goto('https://www.booking.com/')", "language": "node"}))
        self.assertBlocked(self.hook("mcp__firecrawl__firecrawl_scrape", {
            "url": HOTEL_SITE, "actions": [{"type": "executeJavascript", "script": "location='https://airbnb.com'"}]}))

    def test_research_agent_aimed_at_booking_is_blocked(self):
        self.assertBlocked(self.hook("mcp__firecrawl__firecrawl_agent",
                                     {"prompt": "Read the booking.com reviews of Hotel Inventado"}))
        self.assertBlocked(self.hook("mcp__claude_ai_Exa__agent_run", {"query": "Airbnb cave houses in Ciudad Inventada"}))
        self.assertAllowed(self.hook("mcp__firecrawl__firecrawl_agent", {"prompt": "Opening year of Hotel Inventado"}))


class SearchTest(GuardTest):
    def test_plain_search_passes_including_site_booking(self):
        self.open_run()
        cases = [
            ("WebSearch", {"query": "site:booking.com hotel con encanto casco antiguo Ciudad Inventada"}),
            ("mcp__firecrawl__firecrawl_search", {"query": 'site:booking.com "Hotel Inventado" Ciudad Inventada',
                                                  "limit": 5, "excludeDomains": ["tripadvisor.com"]}),
            ("mcp__exa__web_search_exa", {"query": "Booking.com listing for Hotel Inventado in Ciudad Inventada"}),
            ("mcp__claude_ai_Exa__web_search_exa", {"query": "Airbnb cave house Ciudad Inventada"}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                self.assertAllowed(self.hook(tool, tool_input))

    def test_search_that_fetches_booking_or_airbnb_results_is_blocked(self):
        fetch = {"formats": ["markdown"]}
        cases = [
            {"query": 'site:booking.com "Hotel Inventado"', "scrapeOptions": fetch},
            {"query": "airbnb casa cueva Ciudad Inventada", "scrapeOptions": fetch},
            {"query": "hotel inventado reviews", "includeDomains": ["booking.com"], "scrapeOptions": fetch},
        ]
        for tool_input in cases:
            with self.subTest(query=tool_input["query"]):
                self.assertBlocked(self.hook("mcp__firecrawl__firecrawl_search", tool_input))

    def test_any_search_that_fetches_its_result_pages_is_blocked(self):
        # A hotel's name alone brings up its Booking page among the results, which scrapeOptions would fetch.
        fetch = {"formats": ["markdown"]}
        cases = [
            ("mcp__firecrawl__firecrawl_search", {"query": '"Hotel Inventado" Ciudad Inventada', "scrapeOptions": fetch}),
            ("mcp__firecrawl__firecrawl_search", {"query": "hoteles con encanto Ciudad Inventada prensa local",
                                                  "scrapeOptions": fetch, "excludeDomains": ["booking.com"]}),
            ("mcp__plugin_firecrawl_firecrawl__firecrawl_search", {"query": "Hotel Inventado", "scrapeOptions": {}}),
        ]
        for tool, tool_input in cases:
            with self.subTest(tool=tool, query=tool_input["query"]):
                result = self.hook(tool, tool_input)
                self.assertBlocked(result)
                self.assertIn("without scrapeOptions", result.stderr)
                self.assertIn("one by one", result.stderr)


class BashTest(GuardTest):
    def test_commands_that_fetch_booking_or_airbnb_are_blocked(self):
        commands = [
            f"curl -sL '{BOOKING_PAGE}' -o /tmp/page.html",
            f"wget -q {AIRBNB_PAGE}",
            f"cd /tmp && open '{BOOKING_PAGE}'",
            f"python3 -c \"import urllib.request; print(urllib.request.urlopen('{BOOKING_PAGE}').read())\"",
            f"python3 - <<'EOF'\nimport requests\nprint(requests.get('{AIRBNB_PAGE}').text)\nEOF",
            f"node -e \"fetch('{BOOKING_PAGE}').then(r => r.text())\"",
            f"python3 -c \"from playwright.sync_api import sync_playwright\" && echo {BOOKING_PAGE}",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertBlocked(self.hook("Bash", {"command": command, "description": "x"}))

    def test_fetchers_behind_wrappers_shells_and_eval_are_blocked(self):
        commands = [
            f"timeout 20 curl -s '{BOOKING_PAGE}'",
            f"gtimeout 20s curl -s '{BOOKING_PAGE}'",
            f"timeout -k 5 -s KILL 1.5m wget -q {AIRBNB_PAGE}",
            f"stdbuf -oL curl -s '{BOOKING_PAGE}'",
            f"ionice -c 3 curl -s '{BOOKING_PAGE}'",
            f"nice -n 5 curl '{BOOKING_PAGE}'",
            f'bash -c "curl -s {BOOKING_PAGE}"',
            f"sh -c 'wget -qO- {AIRBNB_PAGE}'",
            f'zsh -c "curl -s {BOOKING_PAGE}"',
            f'/bin/bash -e -lc "(curl -s {BOOKING_PAGE})"',
            f"eval curl -s '{BOOKING_PAGE}'",
            f'eval "curl -s {BOOKING_PAGE}"',
            f"cd /tmp && FOO=1 timeout 20 env BAR=2 sh -c 'nice curl -s {BOOKING_PAGE}'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertBlocked(self.hook("Bash", {"command": command}))

    def test_wrapped_ordinary_commands_pass(self):
        commands = [
            f"timeout 20 python3 bin/links.py --name 'Hotel Inventado' # {BOOKING_PAGE}",
            "bash -c \"grep -rn 'booking.com' /tmp/run/\"",
            f"bash bin/report.sh '{BOOKING_PAGE}'",
            f"eval echo '{BOOKING_PAGE}'",
            f"nice -n 5 python3 - <<'EOF'\nopen('/tmp/run/x.jsonl', 'a').write('{BOOKING_PAGE}')\nEOF",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertAllowed(self.hook("Bash", {"command": command}))

    def test_ordinary_commands_pass(self):
        record = json.dumps({"name": "Hotel Inventado", "booking_score": {"source_url": BOOKING_PAGE}})
        commands = [
            f"printf '%s\\n' '{record}' >> /tmp/run/candidates-booking-search.jsonl",
            "grep -rn 'booking.com' /tmp/run/",
            f"python3 bin/links.py --name 'Hotel Inventado' --check-in 2026-11-20 # {BOOKING_PAGE}",
            f"python3 - <<'EOF'\nwith open('/tmp/run/x.jsonl', 'a') as f:\n    f.write('{BOOKING_PAGE}')\nEOF",
            f"python3 - <<'EOF'\nopen('/tmp/run/x.jsonl', 'a').write('{BOOKING_PAGE}')\nEOF",
            f"python3 -c \"from urllib.parse import urlsplit; print(urlsplit('{BOOKING_PAGE}').hostname)\"",
            f"curl -sL '{HOTEL_SITE}' -o /tmp/hotel.html",
            "git status --short",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertAllowed(self.hook("Bash", {"command": command}))


class GmailTest(GuardTest):
    def test_writes_pass_when_no_run_is_open(self):
        self.assertAllowed(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}))
        self.assertAllowed(self.hook("mcp__gmail-personal__create_filter", {"criteria": {}}))

    def test_writes_are_blocked_while_a_run_is_open_in_the_main_conversation_and_a_subagent(self):
        self.open_run()
        for server in GMAIL_SERVERS:
            for tool in GMAIL_WRITES:
                with self.subTest(tool=server + tool):
                    self.assertBlocked(self.hook(server + tool, {"x": 1}), rule="KTD9")
        result = self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}, **SUBAGENT)
        self.assertBlocked(result, rule="KTD9")
        self.assertIn("ciudad-inventada-2026-11", result.stderr)

    def test_reads_pass_while_a_run_is_open(self):
        self.open_run()
        for server in GMAIL_SERVERS:
            for tool in GMAIL_READS:
                with self.subTest(tool=server + tool):
                    self.assertAllowed(self.hook(server + tool, {"query": "from:booking.com"}, **SUBAGENT))

    def test_a_finished_run_is_not_open(self):
        self.open_run(stage="done")
        self.assertAllowed(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}))
        self.assertAllowed(self.hook("mcp__claude-in-chrome__get_page_text", {"tabId": 7}))

    def test_one_open_run_among_finished_ones_counts(self):
        self.open_run(stage="done", trip="pueblo-ficticio-2026-05")
        self.open_run(stage="research", trip="ciudad-inventada-2026-11")
        self.assertBlocked(self.hook("mcp__gmail-work__modify_messages", {"ids": ["1"]}), rule="KTD9")

    def test_unreadable_state_counts_as_open(self):
        run = self.open_run()
        (run / "state.json").write_text("{not json", encoding="utf-8")
        self.assertBlocked(self.hook("mcp__claude_ai_Gmail__reply", {"body": "x"}), rule="KTD9")

    def test_a_run_whose_check_in_has_passed_is_not_open(self):
        run = self.open_run()
        (run / "trip.json").write_text(json.dumps({"check_in": "2020-01-10", "check_out": "2020-01-12"}), encoding="utf-8")
        self.assertAllowed(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}))

    def test_a_run_whose_check_in_is_ahead_is_open(self):
        run = self.open_run()
        (run / "trip.json").write_text(json.dumps({"check_in": "2099-01-10", "check_out": "2099-01-12"}), encoding="utf-8")
        self.assertBlocked(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}), rule="KTD9")

    def test_open_run_reasons_name_the_run_and_a_close_command_that_works(self):
        shutil.copytree(BIN, self.skill / "bin", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        run = self.open_run()
        trip = {"city": "Ciudad Inventada", "city_slug": "ciudad-inventada", "check_in": "2099-11-20",
                "check_out": "2099-11-22", "guests": 2, "budget": {"currency": "EUR", "max": 200}, "dog": False}
        (run / "trip.json").write_text(json.dumps(trip), encoding="utf-8")
        skill = os.path.realpath(self.skill)
        run_dir = f"{skill}/data/trips/ciudad-inventada-2026-11/run"
        close = f'python3 "{skill}/bin/orchestrate.py" close "{run_dir}" --reason abandoned'
        for tool, tool_input in (("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}),
                                 ("mcp__computer-use__screenshot", {})):
            with self.subTest(tool=tool):
                result = self.hook(tool, tool_input)
                self.assertBlocked(result, rule="KTD9")
                self.assertIn(f"({run_dir}, stage shortlist)", result.stderr)
                self.assertIn(close, result.stderr)
        closed = subprocess.run(["sh", "-c", close], capture_output=True, text=True, cwd=str(self.tmp))
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertAllowed(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}))
        self.assertAllowed(self.hook("mcp__computer-use__screenshot", {}))

    def test_missing_data_folder_means_no_run(self):
        (self.skill / "data").unlink()
        self.assertAllowed(self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"}))


class RobustnessTest(GuardTest):
    def test_malformed_stdin_is_allowed_silently(self):
        for raw in ("", "not json", "[1, 2]", '{"tool_name": 5}', '{"hook_event_name": "PreToolUse"}',
                    '{"tool_name": "WebFetch", "tool_input": "https://www.booking.com/"}'):
            with self.subTest(raw=raw):
                self.assertAllowed(self.hook("unused", {}, raw=raw))

    def test_other_tools_pass(self):
        self.open_run()
        self.assertAllowed(self.hook("Read", {"file_path": "/tmp/booking.com.html"}))
        self.assertAllowed(self.hook("Write", {"file_path": "/tmp/x.md", "content": BOOKING_PAGE}))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any folder")
    def test_error_inside_a_check_allows_with_one_line_on_stderr(self):
        self.open_run()
        trips = self.data / "trips"
        trips.chmod(0)
        self.addCleanup(trips.chmod, 0o755)
        result = self.hook("mcp__claude_ai_Gmail__send_message", {"to": "x@example.com"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertIn("guard_hook", result.stderr)


if __name__ == "__main__":
    unittest.main()
