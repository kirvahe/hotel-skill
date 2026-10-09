#!/usr/bin/env python3
"""Reddit adapter for find-hotel: scan a subreddit and read full comment trees (R7, KTD7).

Usage:
    python3 reddit_fetch.py scan SUB (--city NAME [--city NAME ...] | --query REGEX)
                                 [--since YYYY-MM-DD] [--max-pages N] [--out FILE]
                                 [--backend arctic] [--fixtures DIR]
    python3 reddit_fetch.py tree ID_OR_URL [...] [--out FILE] [--backend arctic] [--fixtures DIR]
        ("tree -" reads IDs or URLs from stdin)

scan pages through SUB newest first and keeps the posts whose title or text names one
of the cities (whole word, any case, accents ignored) or matches the query regex.
tree reads every comment of each thread (comments/tree with limit=9999, so nothing is
collapsed); [deleted]/[removed] comments and AutoModerator are skipped.

Output is JSON with "status": complete | partial | failed, and a "reason" whenever the
status is not complete. An unreachable or erroring backend gives "failed" with the
reason, never an empty success. Exit 1 when failed, 0 otherwise, 2 on bad arguments.
With --out the JSON goes to FILE, rewritten after every page or thread and marked
partial until the command finishes, and stdout gets a one-line summary.

Every post, thread and comment carries the fields of a ledger mention: family "reddit",
source_name "r/SUB", url (the permalink of that thread or comment), date; plus score and
body. The research agent adds the quote. Usernames are never output: authors are
dropped and "u/name" in text becomes "u/[user]". Scores freeze in the archive about
36 h after posting; post score and archived_num_comments are stale snapshots.

Backends: "arctic" (Arctic Shift archive). A backend is one class with posts_page,
posts_by_id and comments returning the neutral shapes below; a replacement implements
those three and registers in BACKENDS.

Fixture mode (--fixtures DIR) replays recorded responses instead of the network. Each
DIR/*.json is {"request": {"path": ..., "params": {...}}, "response": {...}}, or has
"error": "..." in place of "response" to record a failure. A request matches when path
and params are equal ("fields" is ignored). A request with no recording fails.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ARCTIC_BASE = "https://arctic-shift.photon-reddit.com/api"
UA = "macos:hotel-skill-reddit-fetch:v1.0 (personal research)"
# Pacing and backoff are the reddit-research skill's scripts/arctic.py values, unchanged:
# keyword queries hit 429 at ~1 req/s in tests; 1 s spacing kept long scans and tree batches clean.
PAUSE = 1.0
# Archive outages in 2026 lasted minutes to hours; 5 tries with growing waits (5, 10, 15, 20 s)
# ride out short overloads, then fail with a reason instead of hanging the session.
RETRIES = 5
BACKOFF = 5
TIMEOUT = 60
PAGE_SIZE = 100
TREE_LIMIT = 9999
IDS_PER_CALL = 500
# 40 pages = 4,000 posts: ~1 min on a fast archive, ~6 min when it is loaded (9 s/page observed).
MAX_PAGES = 40
POST_FIELDS = "id,title,selftext,score,num_comments,created_utc,subreddit"
SKIPPED_BODIES = (None, "[removed]", "[deleted]")
BOTS = ("AutoModerator",)
ID_IN_URL = re.compile(r"/comments/([a-z0-9]+)", re.I)
THREAD_ID = re.compile(r"[a-z0-9]+")
USER_REF = re.compile(r"(?<![A-Za-z0-9_])/?(?:u|user)/[A-Za-z0-9_-]+", re.I)
IN_PROGRESS = "interrupted before finishing"


class BackendError(Exception):
    """The backend could not answer: unreachable, an HTTP error, or a response of the wrong shape."""


def log(*parts):
    print(*parts, file=sys.stderr, flush=True)


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


# --- transports: where raw responses come from -------------------------------------------------

class HttpTransport:
    """GET JSON with the existing scripts' retries: 429 waits for X-RateLimit-Reset, other HTTP
    errors (422 = archive overload), network errors and unreadable bodies back off 5 s x attempt.
    HTTP 400 fails at once: the parameter combination is invalid, retrying cannot help."""

    def __init__(self, base: str = ARCTIC_BASE, sleep=time.sleep):
        self.base, self.sleep = base.rstrip("/"), sleep

    def get(self, path: str, params: dict):
        url = f"{self.base}/{path}?" + urllib.parse.urlencode(params)
        problem = ""
        for attempt in range(1, RETRIES + 1):
            wait = BACKOFF * attempt
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 400:
                    raise BackendError(f"HTTP 400 for {url}: invalid parameter combination") from None
                problem = f"HTTP {error.code}"
                if error.code == 429:
                    wait = max(wait, _int(error.headers.get("X-RateLimit-Reset")) + 1)
            except ValueError as error:
                problem = f"unreadable response ({error})"
            except (OSError, http.client.HTTPException) as error:
                problem = f"network error ({error})"
            if attempt < RETRIES:
                log(f"{problem}, retry {attempt}/{RETRIES} in {wait}s")
                self.sleep(wait)
        raise BackendError(f"unreachable after {RETRIES} attempts (last: {problem}): {url}")


class FixtureTransport:
    """Replays recorded responses from a folder, so tests run offline."""

    IGNORED = ("fields",)

    def __init__(self, folder):
        self.folder = Path(folder)
        self._recordings = None

    @classmethod
    def _key(cls, params) -> dict:
        return {k: str(v) for k, v in (params or {}).items() if k not in cls.IGNORED}

    def _load(self) -> list:
        if self._recordings is None:
            if not self.folder.is_dir():
                raise BackendError(f"fixture folder not found: {self.folder}")
            recordings = []
            for path in sorted(self.folder.glob("*.json")):
                try:
                    rec = json.loads(path.read_text(encoding="utf-8"))
                except ValueError as error:
                    raise BackendError(f"fixture {path.name} is not valid JSON ({error})") from None
                if isinstance(rec, dict) and isinstance(rec.get("request"), dict):
                    recordings.append(rec)
            self._recordings = recordings
        return self._recordings

    def get(self, path: str, params: dict):
        wanted = self._key(params)
        for rec in self._load():
            if rec["request"].get("path") == path and self._key(rec["request"].get("params")) == wanted:
                if rec.get("error"):
                    raise BackendError(f"recorded failure for {path}: {rec['error']}")
                return rec.get("response")
        raise BackendError(f"no recorded response for {path}?{urllib.parse.urlencode(wanted)} in {self.folder}")


# --- backends: one class per Reddit source, returning neutral shapes without authors ------------
#
# post:    {"id", "subreddit", "title", "selftext", "score", "num_comments", "created_utc"}
# comment: {"id", "parent_id", "subreddit", "depth", "score", "created_utc", "is_op", "body"}

def _walk(nodes, depth: int, acc: list) -> list:
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        item = node.get("data", node)
        if not isinstance(item, dict):
            continue
        acc.append((depth, item))
        replies = item.get("replies")
        if isinstance(replies, dict):
            _walk((replies.get("data") or {}).get("children"), depth + 1, acc)
        elif isinstance(replies, list):
            _walk(replies, depth + 1, acc)
    return acc


def _neutral_post(p: dict) -> dict:
    return {"id": p.get("id"), "subreddit": p.get("subreddit"), "title": p.get("title") or "",
            "selftext": p.get("selftext") or "", "score": p.get("score"),
            "num_comments": p.get("num_comments"), "created_utc": p.get("created_utc")}


class ArcticBackend:
    """Arctic Shift archive (no key). Expected to stop updating around March 2027; its history stays."""

    name = "arctic"
    base = ARCTIC_BASE

    def __init__(self, transport, sleep=time.sleep):
        self.transport, self.sleep, self.requests = transport, sleep, 0

    def _data(self, path: str, **params) -> list:
        if self.requests:
            self.sleep(PAUSE)
        self.requests += 1
        response = self.transport.get(path, params)
        if not isinstance(response, dict) or response.get("error") or "data" not in response:
            detail = response.get("error") if isinstance(response, dict) else None
            raise BackendError(f"unexpected response from {path}: {detail or 'no data field'}")
        data = response["data"] or []
        if not isinstance(data, list):
            raise BackendError(f"unexpected response from {path}: data is not a list")
        return [d for d in data if isinstance(d, dict)]

    def posts_page(self, sub: str, cursor=None):
        """One page of SUB, newest first. Returns (posts, cursor for the next page or None at the end)."""
        params = dict(subreddit=sub, limit=PAGE_SIZE, sort="desc", fields=POST_FIELDS)
        if cursor is not None:
            params["before"] = cursor
        batch = self._data("posts/search", **params)
        cursor = batch[-1].get("created_utc") if len(batch) >= PAGE_SIZE else None
        return [_neutral_post(p) for p in batch], cursor

    def posts_by_id(self, ids: list) -> dict:
        meta = {}
        for i in range(0, len(ids), IDS_PER_CALL):
            for p in self._data("posts/ids", ids=",".join(ids[i:i + IDS_PER_CALL]), fields=POST_FIELDS):
                meta[p.get("id")] = _neutral_post(p)
        return meta

    def comments(self, thread_id: str) -> list:
        nodes = _walk(self._data("comments/tree", link_id=thread_id, limit=TREE_LIMIT), 0, [])
        return [{"id": c.get("id"), "parent_id": c.get("parent_id"), "subreddit": c.get("subreddit"),
                 "depth": depth, "score": c.get("score"), "created_utc": c.get("created_utc"),
                 "is_op": bool(c.get("is_submitter")), "body": c.get("body")}
                for depth, c in nodes
                if c.get("body") not in SKIPPED_BODIES and c.get("author") not in BOTS]


BACKENDS = {"arctic": ArcticBackend}


def make_backend(name: str = "arctic", fixtures=None):
    cls = BACKENDS[name]
    if fixtures:
        return cls(FixtureTransport(fixtures), sleep=lambda seconds: None)
    return cls(HttpTransport(base=cls.base), sleep=time.sleep)


# --- commands: backend-independent matching, permalinks and status ------------------------------

def _day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) else None


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def redact(text):
    return USER_REF.sub("u/[user]", text) if text else text


def thread_url(sub, thread_id: str) -> str:
    return f"https://www.reddit.com/r/{sub}/comments/{thread_id}/" if sub else \
        f"https://www.reddit.com/comments/{thread_id}/"


def _source(sub):
    return f"r/{sub}" if sub else None


def _save(result: dict, out):
    if not out:
        return
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _finish(result: dict, status: str, reason: str, out) -> dict:
    result["status"], result["reason"] = status, reason
    _save(result, out)
    return result


def _city_pattern(cities):
    names = [_fold(c).strip() for c in cities or () if c and c.strip()]
    if not names:
        return None
    return re.compile("|".join(rf"(?<!\w){re.escape(n)}(?!\w)" for n in names))


def scan(backend, sub: str, cities=(), query=None, since=None, max_pages: int = MAX_PAGES, out=None) -> dict:
    """Posts of SUB that name a city or match the query, newest first, each with its thread permalink."""
    sub = re.sub(r"^/?r/", "", sub.strip())
    since_ts = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() if since else 0
    city_re = _city_pattern(cities)
    query_re = re.compile(query, re.I) if query else None
    result = {"status": "partial", "reason": IN_PROGRESS, "backend": backend.name, "command": "scan",
              "subreddit": sub, "cities": list(cities or ()), "query": query, "since": since,
              "pages": 0, "scanned": 0, "reached": None, "posts": []}
    cursor = None
    for page in range(1, max_pages + 1):
        try:
            posts, cursor = backend.posts_page(sub, cursor)
        except BackendError as error:
            if page == 1:
                return _finish(result, "failed", str(error), out)
            return _finish(result, "partial", f"backend failed on page {page} after {page - 1} page(s): {error}", out)
        if page == 1 and not posts:
            return _finish(result, "failed", f"r/{sub} returned no posts at all: check the subreddit name", out)
        fresh = [p for p in posts if (p["created_utc"] or 0) >= since_ts]
        result["pages"] = page
        result["scanned"] += len(fresh)
        if fresh:
            result["reached"] = _day(fresh[-1]["created_utc"])
        for p in fresh:
            text = f"{p['title']}\n{p['selftext']}"
            folded = _fold(text)
            matched = []
            if city_re and city_re.search(folded):
                matched.append("city")
            if query_re and (query_re.search(text) or query_re.search(folded)):
                matched.append("query")
            if matched:
                psub = p["subreddit"] or sub
                result["posts"].append({
                    "id": p["id"], "url": thread_url(psub, p["id"]), "family": "reddit", "source_name": _source(psub),
                    "date": _day(p["created_utc"]), "score": p["score"], "archived_num_comments": p["num_comments"],
                    "title": redact(p["title"]), "body": redact(p["selftext"]), "matched": matched})
        _save(result, out)
        if len(fresh) < len(posts) or cursor is None:
            return _finish(result, "complete", "", out)
        log(f"page {page}: {result['scanned']} posts, back to {result['reached']}")
    return _finish(result, "partial",
                   f"stopped at --max-pages {max_pages} (reached {result['reached']}); raise it or narrow --since", out)


def _thread_id(ref: str):
    ref = (ref or "").strip()
    match = ID_IN_URL.search(ref)
    tid = (match.group(1) if match else ref).lower()
    if tid.startswith("t3_"):
        tid = tid[3:]
    return tid if THREAD_ID.fullmatch(tid) else None


def _thread_record(tid: str, post: dict, comments: list) -> dict:
    sub = post.get("subreddit") or next((c["subreddit"] for c in comments if c.get("subreddit")), None)
    mentions = []
    for c in comments:
        csub = c.get("subreddit") or sub
        mentions.append({
            "id": c["id"], "url": f"{thread_url(csub, tid)}comment/{c['id']}/", "family": "reddit",
            "source_name": _source(csub), "date": _day(c["created_utc"]), "score": c["score"],
            "depth": c["depth"], "parent_id": c["parent_id"], "is_op": c["is_op"], "body": redact(c["body"])})
    return {"id": tid, "url": thread_url(sub, tid), "family": "reddit", "source_name": _source(sub),
            "date": _day(post.get("created_utc")), "title": redact(post.get("title")),
            "body": redact(post.get("selftext")), "post_score": post.get("score"),
            # comment_count = what was fetched; archived_num_comments = stale snapshot, often lower
            "comment_count": len(mentions), "archived_num_comments": post.get("num_comments"),
            "empty": not mentions, "mentions": mentions}


def fetch_trees(backend, refs, out=None) -> dict:
    """Full comment tree of every thread; stops at the first backend failure and lists what was not read."""
    ids, failed = [], []
    for ref in refs:
        tid = _thread_id(ref)
        if tid is None:
            failed.append({"id": ref, "reason": "not a Reddit thread id or URL"})
        elif tid not in ids:
            ids.append(tid)
    result = {"status": "partial", "reason": IN_PROGRESS, "backend": backend.name, "command": "tree",
              "threads_read": 0, "comments": 0, "threads": [], "failed": failed, "empty_threads": []}
    if not ids:
        return _finish(result, "failed", "no valid thread ids or URLs given", out)
    try:
        meta = backend.posts_by_id(ids)
    except BackendError as error:
        failed += [{"id": t, "reason": "not attempted: the backend failed before reading threads"} for t in ids]
        return _finish(result, "failed", str(error), out)
    for n, tid in enumerate(ids):
        try:
            comments = backend.comments(tid)
        except BackendError as error:
            failed.append({"id": tid, "reason": str(error)})
            failed += [{"id": t, "reason": f"not attempted: the backend failed on {tid}"} for t in ids[n + 1:]]
            status = "partial" if result["threads"] else "failed"
            return _finish(result, status, f"backend failed on thread {tid}: {error}", out)
        thread = _thread_record(tid, meta.get(tid) or {}, comments)
        result["threads"].append(thread)
        if thread["empty"]:
            result["empty_threads"].append(tid)
            log(f"{tid}\tEMPTY (removed post or no archived replies): does not count as read")
        else:
            result["threads_read"] += 1
            result["comments"] += thread["comment_count"]
            log(f"{tid}\t{thread['comment_count']} comments\t{thread['source_name']}")
        _save(result, out)
    if failed:
        return _finish(result, "partial", f"{len(failed)} input(s) were not thread ids or URLs", out)
    return _finish(result, "complete", "", out)


def main(argv: list) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--backend", choices=sorted(BACKENDS), default="arctic")
    common.add_argument("--fixtures", metavar="DIR", help="replay recorded responses from DIR (offline tests)")
    common.add_argument("--out", metavar="FILE", help="write the JSON here; stdout gets a summary")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", parents=[common])
    p_scan.add_argument("sub")
    p_scan.add_argument("--city", action="append", default=[], help="city name; repeat for other spellings")
    p_scan.add_argument("--query", help="regex matched against title and text, any case")
    p_scan.add_argument("--since", help="YYYY-MM-DD: skip older posts")
    p_scan.add_argument("--max-pages", type=int, default=MAX_PAGES)
    p_tree = sub.add_parser("tree", parents=[common])
    p_tree.add_argument("refs", nargs="+", metavar="ID_OR_URL")
    args = parser.parse_args(argv[1:])

    backend = make_backend(args.backend, args.fixtures)
    out = Path(args.out).expanduser() if args.out else None
    if args.cmd == "scan":
        if not args.city and not args.query:
            p_scan.error("give --city NAME (repeatable) or --query REGEX")
        if args.max_pages < 1:
            p_scan.error("--max-pages must be at least 1")
        try:
            if args.since:
                datetime.strptime(args.since, "%Y-%m-%d")
            if args.query:
                re.compile(args.query)
        except (ValueError, re.error) as error:
            p_scan.error(str(error))
        result = scan(backend, args.sub, cities=args.city, query=args.query, since=args.since,
                      max_pages=args.max_pages, out=out)
        summary = {"posts": len(result["posts"]), "scanned": result["scanned"], "reached": result["reached"]}
    else:
        refs = sys.stdin.read().split() if args.refs == ["-"] else args.refs
        result = fetch_trees(backend, refs, out=out)
        summary = {"threads_read": result["threads_read"], "comments": result["comments"],
                   "empty_threads": len(result["empty_threads"]), "failed": len(result["failed"])}
    if out:
        print(json.dumps({"status": result["status"], "reason": result["reason"], "out": str(out), **summary},
                         ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
