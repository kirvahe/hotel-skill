#!/usr/bin/env python3
"""PreToolUse guard for the /hotel skill: no Booking or Airbnb automation (R21, KTD9).

The skill's frontmatter registers this hook, and the installer writes this script's absolute
path into the hook command; bin/settings_hook.py registers the same command in the Claude Code
settings file, the only place whose hooks also run for subagents. Claude Code then runs it before
every tool call that MATCHER (below) matches, with the hook JSON on stdin: tool_name, tool_input,
cwd, session_id, and agent_id / agent_type when the call comes from a subagent. MATCHER is built
from the server lists below: it covers the tools decide() acts on and leaves other MCP servers out.

Always blocked:
  - browser and screen tools whose input names a Booking or Airbnb host, in a URL or in any
    other text (typed text, page scripts);
  - fetch, scrape, crawl, map, extract, interact and research-agent calls aimed at a Booking or
    Airbnb URL: every URL field is checked, with URLs embedded in another URL (proxies,
    percent-encoded parameters, a host written without a scheme in the path or query, as
    translate, cache and archive URLs carry it) and the browser code these calls carry;
  - searches that also fetch their result pages (Firecrawl scrapeOptions), whatever the query:
    a hotel's results often include its Booking page, and the research contract never passes
    scrapeOptions. A plain search passes, `site:booking.com` included, because Booking scores
    come from search results (R23);
  - Bash commands that name a Booking or Airbnb host and fetch something (curl, wget, open,
    urllib.request, requests, fetch(...), a headless browser), also behind wrappers (timeout,
    nice -n 5, env, sudo), eval and sh -c "...".
Blocked only while a find-hotel run is open:
  - Gmail tools (any MCP server with "gmail" in its name) outside the read-only list;
  - browser and screen calls that name no URL (a tab read, a click, a screenshot).

A run is open when any data/trips/*/run folder (bin/ledger.py) has a stage other than "done" and
its check-in date (trip.json) has not passed. A run folder without state.json is at "intake" (as
ledger.read_state reads it); a state file that cannot be parsed, or a trip.json without a
readable check-in, counts as open. There is no age limit: an unfinished run stays open until its
check-in date or until the skill closes it, because the skill resumes open runs. The guard runs in
every session, so these block reasons name the run's absolute path and the orchestrate.py close
command that ends it.

Host rule: booking.com and its subdomains, and any host with an "airbnb" label (refused_host,
which bin/engine_reader.py imports from here).

Output: a block prints the deny JSON on stdout and the same reason on stderr, and exits 2
(exit 2 blocks even if the JSON format changes). A pass prints nothing and exits 0. Malformed
input passes silently; an error inside a check passes with one line on stderr, so a bug never
breaks every tool call. No network, no imports beyond the standard library. The hook runs before
every matched tool call, so importing it stays cheap and does nothing else: modules only one check
needs (datetime) are imported inside that check.

Usage (as Claude Code runs it):
    python3 /abs/skill/bin/guard_hook.py < hook-input.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import unquote, urlsplit

BROWSER_SERVERS = ("playwright", "claude-in-chrome", "computer-use", "cmux-cua", "Claude_Browser", "remote-devices")
FETCH_SERVERS = ("firecrawl", "fetch", "exa", "claude_ai_Exa")
# The hook's matcher (SKILL.md and the settings file) covers every tool decide() acts on: Bash, WebFetch,
# the tools of a browser or fetch server, directly or bundled by a plugin (mcp__plugin_<plugin>_<server>,
# see _on), and the tools of any server with "gmail" in its name, in any case. Other MCP servers never
# start the hook. Claude Code reads it as a JavaScript regex; server names hold only letters, digits, "_"
# and "-", so they need no escaping.
MATCHER = ("^(Bash|WebFetch|mcp__(plugin_(.*_)?)?(" + "|".join(BROWSER_SERVERS + FETCH_SERVERS) + ")(__.*)?"
           "|mcp__.*[Gg][Mm][Aa][Ii][Ll].*)$")
GMAIL_READS = frozenset({"search_threads", "get_thread", "get_message", "list_labels", "list_drafts", "get_draft",
                         "mailbox_info", "list_filters", "list_events", "get_event", "list_calendars"})
# Fields that hold code a browser runs (page scripts, Firecrawl interact code).
CODE_KEYS = frozenset({"code", "script", "function", "javascript", "js"})
# Fields of research-agent and interact calls that say where to go.
TASK_KEYS = ("prompt", "query", "systemPrompt")

# Host names inside free text ("www.booking.com" in a URL, "site:booking.com", "airbnb.es"), as hosts_in_text
# reads them: runs of word characters and hyphens, a label (1-63 letters, digits or hyphens, no hyphen at
# either end), and a top-level label (2-63 letters).
WORD_RUN = re.compile(r"[\w-]+")
LABEL = re.compile(r"(?i)[a-z0-9-]{1,63}")
TOP_LABEL = re.compile(r"(?i)[a-z]{2,63}")
# Every http(s) scheme in a string, so a URL embedded in another URL is checked too.
SCHEME = re.compile(r"(?i)https?:/+")
AUTHORITY_END = re.compile(r"[/?#]")
AIRBNB_WORD = re.compile(r"(?i)\bairbnb\b")

# Bash: programs that fetch when they start a command, and fetching code inside a command.
SHELL_FETCHERS = frozenset({"curl", "wget", "aria2c", "lynx", "w3m", "links", "elinks", "open", "xdg-open", "osascript",
                            "http", "https", "xh", "httpie", "chromium", "chromium-browser", "google-chrome", "chrome",
                            "firefox", "safari", "playwright"})
SHELL_WRAPPERS = frozenset({"sudo", "env", "command", "exec", "nohup", "time", "xargs", "then", "do", "else",
                            "builtin", "nice", "caffeinate", "timeout", "gtimeout", "stdbuf", "ionice", "eval"})
# Shells whose -c option makes the next word the command they run (bash -c "curl ...", sh -lc '...').
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
SHELL_STRING_OPTION = re.compile(r"-[A-Za-z]*c[A-Za-z]*")
# Option values a wrapper takes: a count or a duration (nice -n 5, timeout 1.5m), a signal (timeout -s KILL).
WRAPPER_VALUE = re.compile(r"\d[\d.]*[smhd]?|(?:SIG)?[A-Z]+[0-9]*")
SHELL_SEGMENTS = re.compile(r"\$\(|`|&&|\|\||[;&|\n]")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
CODE_FETCH = re.compile(
    r"\burlopen\b|\burllib\.request\b|\burllib3\b|\brequests\.(?:get|post|head|put|request|Session)\b|\bhttpx\b"
    r"|\baiohttp\b|\bhttp\.client\b|\bpycurl\b|\bmechanize\b|\bwebbrowser\b|\bplaywright\b|\bpuppeteer\b"
    r"|\bselenium\b|\bfetch\s*\(|\baxios\b|\bhttps?\.(?:get|request)\s*\(|\bInvoke-(?:WebRequest|RestMethod)\b"
    r"|\bNet::HTTP\b|\bopen-uri\b|\bLWP::")

PREFIX = "Blocked by the /hotel guard"


def refused_host(url: str) -> str | None:
    """The host when the URL is a Booking or Airbnb page (R21), else None."""
    host = (urlsplit(url).hostname or "").rstrip(".")
    if host == "booking.com" or host.endswith(".booking.com") or "airbnb" in host.split("."):
        return host
    return None


def _host(url: str) -> str:
    """The host of a URL, read as http when it has no scheme; empty when it has none."""
    text = url.strip()
    if "://" not in text[:16]:
        text = "http://" + text.lstrip("/")
    try:
        return (urlsplit(text).hostname or "").rstrip(".")
    except ValueError:
        return ""


def _refused(host: str) -> str | None:
    return refused_host("http://" + host) if host else None


def _authority_end(text: str, start: int) -> int:
    """Where the host part that begins at start ends: just past the first / ? or # from there, else the
    end of text. Keeping that character keeps the parse _host makes of the whole rest of the text."""
    found = AUTHORITY_END.search(text, start)
    return found.end() if found else len(text)


def _path_and_query(url: str) -> str:
    """The path and query of a URL, read as http when it has no scheme; all of it when it cannot be parsed."""
    text = url.strip()
    if "://" not in text[:16]:
        text = "http://" + text.lstrip("/")
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    return parts.path + "?" + parts.query


def _forms(text: str) -> list:
    """The text as written and percent-decoded (twice, for double encoding)."""
    decoded = unquote(unquote(text))
    return [text] if decoded == text else [text, decoded]


def hosts_in_text(text: str):
    """Every host name in free text, in order, in one pass over the text.

    The text is read as runs of word characters and hyphens ([\\w-]+) and the characters between
    them. A chain is a sequence of runs joined by single dots in which every run but the last is a
    label. A chain names one host: from its first run, if that run is a label, to the last run after
    it that is a top-level label. That is what the regex
    (?<![\\w-])((?:label\\.)+[a-z]{2,63})(?![\\w-]) finds with findall (tests/test_guard_hook.py keeps it
    as the reference), without the time that regex takes on long chains: over 40 s on 64 KB.
    """
    start = end = None  # where the current chain starts, and where its last top-level label ends
    previous_end, previous_is_label = -2, False
    for run in WORD_RUN.finditer(text):
        word = run.group()
        if previous_is_label and run.start() == previous_end + 1 and text[previous_end] == ".":
            if TOP_LABEL.fullmatch(word):
                end = run.end()
        else:
            if end is not None:
                yield text[start:end]
            start, end = run.start(), None
        previous_end = run.end()
        previous_is_label = word[0] != "-" and word[-1] != "-" and LABEL.fullmatch(word) is not None
    if end is not None:
        yield text[start:end]


def refused_in_text(text: str) -> str | None:
    """The first Booking or Airbnb host named anywhere in free text.

    Every refused host holds "booking" or "airbnb", so text without either skips the host scan.
    """
    for form in _forms(text):
        lowered = form.lower()
        if "booking" not in lowered and "airbnb" not in lowered:
            continue
        for host in hosts_in_text(form):
            if _refused(host.lower()):
                return host.lower()
    return None


def refused_in_url(value: str) -> str | None:
    """The Booking or Airbnb host a URL field is aimed at.

    That is the URL's own host, the host of a URL embedded in it with a scheme (a reader proxy), or a
    host named without a scheme in its path or query (translate?u=www.booking.com/...,
    cache:www.booking.com/..., web.archive.org/web/2025/www.booking.com/...).
    """
    for form in _forms(value):
        # An embedded URL's host ends at the first / ? or # after its scheme, so _host reads only up to
        # there: parsing the whole rest of the string for each of thousands of embedded URLs is quadratic.
        hosts = [_host(form)] + [_host(form[m.start():_authority_end(form, m.end())])
                                 for m in SCHEME.finditer(form) if m.start() > 0]
        for host in hosts:
            if _refused(host):
                return host
        host = refused_in_text(_path_and_query(form))
        if host:
            return host
    return None


def targets_booking_or_airbnb(text: str) -> bool:
    """A query or task that aims at Booking or Airbnb: a host such as site:booking.com, or the word airbnb."""
    return bool(refused_in_text(text) or AIRBNB_WORD.search(text))


def _strings(value):
    """Every string inside a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _is_url_key(key: str) -> bool:
    k = key.lower()
    return k in ("uri", "href", "link", "links") or k.endswith(("url", "urls", "_uri"))


def _keyed_strings(value, wanted):
    """Every string held, at any depth, under a key for which wanted(key) is true."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and wanted(key):
                yield from _strings(item)
            elif isinstance(item, (dict, list)):
                yield from _keyed_strings(item, wanted)
    elif isinstance(value, list):
        for item in value:
            yield from _keyed_strings(item, wanted)


def split_tool(name: str) -> tuple:
    """("server", "tool") for an MCP tool name mcp__<server>__<tool>, else ("", name)."""
    if not name.startswith("mcp__"):
        return "", name
    server, _, tool = name[len("mcp__"):].partition("__")
    return server, tool


def _on(server: str, names) -> bool:
    """The server is one of names, directly or bundled by a plugin (mcp__plugin_<plugin>_<server>__)."""
    return server in names or (server.startswith("plugin_") and server.endswith(tuple("_" + n for n in names)))


def _skill_dir() -> str:
    """The folder that holds this bin/ directory."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def open_run(skill_dir: str | None = None) -> str | None:
    """The absolute path of the first run folder whose stage is not done, else None.

    skill_dir defaults to the folder that holds this bin/ directory.
    """
    trips = os.path.join(os.path.abspath(skill_dir or _skill_dir()), "data", "trips")
    if not os.path.isdir(trips):
        return None
    for entry in sorted(os.scandir(trips), key=lambda e: e.name):
        run = os.path.join(entry.path, "run")
        if os.path.isdir(run):
            stage = _stage(os.path.join(run, "state.json"))
            if stage != "done" and not _check_in_passed(os.path.join(run, "trip.json")):
                return run
    return None


def _run_is_open(run: str) -> str:
    """The start of a KTD9 block reason: which run is open and at what stage."""
    return f"a find-hotel run is open ({run}, stage {_stage(os.path.join(run, 'state.json'))})"


def _how_to_close(run: str) -> str:
    """The end of a KTD9 block reason: the command that ends the run, so any session can lift the block."""
    return (f"If the user has abandoned that search, close the run: "
            f'python3 "{_skill_dir()}/bin/orchestrate.py" close "{run}" --reason abandoned')


def _read_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _check_in_passed(path: str) -> bool:
    from datetime import date  # only open runs need it; the hook's import stays cheap
    try:
        return date.fromisoformat(_read_json(path)["check_in"]) < date.today()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def _stage(path: str) -> str:
    try:
        stage = _read_json(path).get("stage")
    except FileNotFoundError:
        return "intake"
    except (OSError, ValueError, AttributeError):
        return "unreadable"
    return stage if isinstance(stage, str) and stage else "unreadable"


def check_browser(tool: str, tool_input: dict) -> str | None:
    for text in _strings(tool_input):
        host = refused_in_text(text)
        if host:
            return f"{PREFIX} (R21): {tool} would open {host}. The skill never automates Booking or Airbnb; give the user a link instead."
    hosts = [_host(value) for value in _keyed_strings(tool_input, _is_url_key)]
    if any("." in host or host == "localhost" for host in hosts):
        return None
    run = open_run()
    if run:
        return (f"{PREFIX} (KTD9): {_run_is_open(run)}; a browser or screen call must name the URL it acts on. "
                f"Booking engines are read through bin/engine_reader.py. {_how_to_close(run)}")
    return None


def check_fetch(tool: str, tool_input: dict) -> str | None:
    for value in _keyed_strings(tool_input, _is_url_key):
        host = refused_in_url(value)
        if host:
            return f"{PREFIX} (R21): {tool} would fetch {host}. Booking and Airbnb pages are never read; use search-result text or a link the user opens."
    for text in _keyed_strings(tool_input, lambda key: key.lower() in CODE_KEYS):
        host = refused_in_text(text)
        if host:
            return f"{PREFIX} (R21): {tool} carries browser code that opens {host}."
    _, name = split_tool(tool)
    if name.endswith("_search") and tool_input.get("scrapeOptions") is not None:
        return (f"{PREFIX} (R21): {tool} with scrapeOptions also fetches every result page, and a hotel's results "
                f"often include its Booking page. Search without scrapeOptions and read the pages you need one by one.")
    if "agent" in name or "interact" in name:
        task = " ".join(_strings([tool_input.get(key) for key in TASK_KEYS]))
        if targets_booking_or_airbnb(task):
            return f"{PREFIX} (R21): {tool} would read Booking or Airbnb pages. Use a plain search instead."
    return None


def _command_names(command: str):
    """The program that starts each simple command.

    That is the first word after assignments, after wrappers such as sudo, env, timeout or eval with
    their options and option values, and inside the string that sh -c (bash, zsh...) runs. Quotes
    and a leading ( { ! are stripped from each word, so eval "curl ..." and bash -c "(curl ...)" read curl.
    """
    for segment in SHELL_SEGMENTS.split(command):
        words = iter(segment.split())
        wrapped = False
        for word in words:
            word = word.lstrip("({!'\"").rstrip("'\"")
            if not word or ASSIGNMENT.match(word) or (wrapped and (word[0] == "-" or WRAPPER_VALUE.fullmatch(word))):
                continue
            name = word.rsplit("/", 1)[-1]
            if name in SHELL_WRAPPERS or (name in SHELLS and _runs_a_string(words)):
                wrapped = True
                continue
            yield name
            break


def _runs_a_string(words) -> bool:
    """True when a shell's options, read from words up to its first other word, include -c."""
    for word in words:
        if not word.startswith("-"):
            return False
        if SHELL_STRING_OPTION.fullmatch(word):
            return True
    return False


def check_bash(tool_input: dict) -> str | None:
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    host = refused_in_text(command)
    if host and (CODE_FETCH.search(command) or any(name in SHELL_FETCHERS for name in _command_names(command))):
        return f"{PREFIX} (R21): this command fetches {host}. Booking and Airbnb pages are never fetched; build a link for the user instead."
    return None


def check_gmail(tool: str, name: str) -> str | None:
    if name in GMAIL_READS:
        return None
    run = open_run()
    if run:
        return f"{PREFIX} (KTD9): {_run_is_open(run)}, so Gmail is read-only; {tool} is not a read tool. {_how_to_close(run)}"
    return None


def decide(event: dict) -> str | None:
    """The block reason for one PreToolUse event, or None to let the call through."""
    if event.get("hook_event_name", "PreToolUse") != "PreToolUse":
        return None
    tool, tool_input = event.get("tool_name"), event.get("tool_input")
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return None
    if tool == "Bash":
        return check_bash(tool_input)
    if tool == "WebFetch":
        return check_fetch(tool, tool_input)
    server, name = split_tool(tool)
    if not server:
        return None
    if _on(server, BROWSER_SERVERS):
        return check_browser(tool, tool_input)
    if _on(server, FETCH_SERVERS):
        return check_fetch(tool, tool_input)
    if "gmail" in server.lower():  # any Gmail server, whatever the user named it
        return check_gmail(tool, name)
    return None


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    try:
        reason = decide(event)
    except Exception as error:  # a bug in a check must not break every tool call
        detail = f"{type(error).__name__}: {error}".splitlines()[0] if str(error) else type(error).__name__
        print(f"guard_hook: check failed, call allowed ({detail})", file=sys.stderr)
        return 0
    if reason is None:
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
