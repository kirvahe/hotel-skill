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
    percent-encoded parameters) and the browser code these calls carry;
  - searches that also fetch result pages (Firecrawl scrapeOptions) when the query or the
    included domains target Booking or Airbnb. A plain search passes, `site:booking.com`
    included, because Booking scores come from search results (R23);
  - Bash commands that name a Booking or Airbnb host and fetch something (curl, wget, open,
    urllib.request, requests, fetch(...), a headless browser).
Blocked only while a find-hotel run is open:
  - Gmail tools (any MCP server with "gmail" in its name) outside the read-only list;
  - browser and screen calls that name no URL (a tab read, a click, a screenshot).

A run is open when any data/trips/*/run folder (bin/ledger.py) has a stage other than "done" and
its check-in date (trip.json) has not passed. A run folder without state.json is at "intake" (as
ledger.read_state reads it); a state file that cannot be parsed, or a trip.json without a
readable check-in, counts as open. There is no age limit: an unfinished run stays open until its
check-in date or until the skill closes it, because the skill resumes open runs.

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

# A host name inside free text: "www.booking.com" in a URL, "site:booking.com", "airbnb.es".
HOST_IN_TEXT = re.compile(r"(?i)(?<![\w-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(?![\w-])")
# Every http(s) scheme in a string, so a URL embedded in another URL is checked too.
SCHEME = re.compile(r"(?i)https?:/+")
AIRBNB_WORD = re.compile(r"(?i)\bairbnb\b")

# Bash: programs that fetch when they start a command, and fetching code inside a command.
SHELL_FETCHERS = frozenset({"curl", "wget", "aria2c", "lynx", "w3m", "links", "elinks", "open", "xdg-open", "osascript",
                            "http", "https", "xh", "httpie", "chromium", "chromium-browser", "google-chrome", "chrome",
                            "firefox", "safari", "playwright"})
SHELL_WRAPPERS = frozenset({"sudo", "env", "command", "exec", "nohup", "time", "xargs", "then", "do", "else",
                            "builtin", "nice", "caffeinate"})
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


def _forms(text: str) -> list:
    """The text as written and percent-decoded (twice, for double encoding)."""
    decoded = unquote(unquote(text))
    return [text] if decoded == text else [text, decoded]


def refused_in_text(text: str) -> str | None:
    """The first Booking or Airbnb host named anywhere in free text.

    Every refused host holds "booking" or "airbnb", so text without either skips the host scan,
    which is slow on long dotted strings.
    """
    for form in _forms(text):
        lowered = form.lower()
        if "booking" not in lowered and "airbnb" not in lowered:
            continue
        for host in HOST_IN_TEXT.findall(form):
            if _refused(host.lower()):
                return host.lower()
    return None


def refused_in_url(value: str) -> str | None:
    """The Booking or Airbnb host a URL field is aimed at, directly or through an embedded URL."""
    for form in _forms(value):
        hosts = [_host(form)] + [_host(form[m.start():]) for m in SCHEME.finditer(form) if m.start() > 0]
        for host in hosts:
            if _refused(host):
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


def open_run(skill_dir: str | None = None) -> str | None:
    """'trips/<trip>/run (stage X)' for the first run whose stage is not done, else None.

    skill_dir defaults to the folder that holds this bin/ directory.
    """
    skill_dir = skill_dir or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    trips = os.path.join(skill_dir, "data", "trips")
    if not os.path.isdir(trips):
        return None
    for entry in sorted(os.scandir(trips), key=lambda e: e.name):
        run = os.path.join(entry.path, "run")
        if os.path.isdir(run):
            stage = _stage(os.path.join(run, "state.json"))
            if stage != "done" and not _check_in_passed(os.path.join(run, "trip.json")):
                return f"trips/{entry.name}/run, stage {stage}"
    return None


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
        return (f"{PREFIX} (KTD9): a find-hotel run is open ({run}); a browser or screen call must name the URL "
                f"it acts on. Booking engines are read through bin/engine_reader.py.")
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
        aim = " ".join(_strings([tool_input.get("query"), tool_input.get("includeDomains")]))
        if targets_booking_or_airbnb(aim):
            return (f"{PREFIX} (R21): this search also fetches its result pages (scrapeOptions) and targets "
                    f"Booking or Airbnb. Run it without scrapeOptions.")
    if "agent" in name or "interact" in name:
        task = " ".join(_strings([tool_input.get(key) for key in TASK_KEYS]))
        if targets_booking_or_airbnb(task):
            return f"{PREFIX} (R21): {tool} would read Booking or Airbnb pages. Use a plain search instead."
    return None


def _command_names(command: str):
    """The program that starts each simple command, after assignments and wrappers like sudo or env."""
    for segment in SHELL_SEGMENTS.split(command):
        words = segment.strip().lstrip("({!").split()
        wrapped = False
        for word in words:
            word = word.strip("'\"")
            if ASSIGNMENT.match(word) or (wrapped and word.startswith("-")):
                continue
            name = word.rsplit("/", 1)[-1]
            if name in SHELL_WRAPPERS:
                wrapped = True
                continue
            yield name
            break


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
        return f"{PREFIX} (KTD9): a find-hotel run is open ({run}), so Gmail is read-only; {tool} is not a read tool."
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
