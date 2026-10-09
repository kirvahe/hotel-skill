"""Tests for bin/reddit_fetch.py: the Reddit adapter (subreddit scan and full comment trees).

All data here is made up: subs, threads, comments and author names are synthetic.
Fixtures are recorded request/response pairs in the Arctic Shift response shape.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent.parent / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reddit"
sys.path.insert(0, str(BIN))

import ledger  # noqa: E402
import reddit_fetch  # noqa: E402

THREAD = "https://www.reddit.com/r/primeriatravel/comments/tg0001/"
KEPT_COMMENTS = {"tc0001": (42, 0), "tc0002": (7, 1), "tc0003": (1, 2), "tc0004": (15, 0), "tc0007": (-3, 0)}


def setUpModule():
    quiet = mock.patch.object(reddit_fetch, "log", lambda *parts: None)  # progress lines go to stderr
    quiet.start()
    unittest.addModuleCleanup(quiet.stop)


def fixture_backend(folder=FIXTURES):
    return reddit_fetch.make_backend("arctic", fixtures=folder)


def cli(*args):
    result = subprocess.run([sys.executable, str(BIN / "reddit_fetch.py"), *map(str, args)],
                            capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def record(folder: Path, name: str, path: str, params: dict, response=None, error=None):
    rec = {"request": {"path": path, "params": params}}
    if error:
        rec["error"] = error
    else:
        rec["response"] = response
    (folder / name).write_text(json.dumps(rec), encoding="utf-8")


def tree_mentions(result):
    return [m for thread in result["threads"] for m in thread["mentions"]]


class TreeTest(unittest.TestCase):
    def test_recorded_tree_yields_every_comment_with_permalink_and_score(self):
        result = reddit_fetch.fetch_trees(fixture_backend(), ["tg0001"])
        self.assertEqual(result["status"], "complete", result.get("reason"))
        self.assertEqual(len(result["threads"]), 1)
        thread = result["threads"][0]
        self.assertEqual(thread["url"], THREAD)
        self.assertEqual(thread["comment_count"], 5)
        mentions = {m["id"]: m for m in thread["mentions"]}
        # every real comment, at every depth; [deleted] and AutoModerator are not comments to read
        self.assertEqual(set(mentions), set(KEPT_COMMENTS))
        for cid, (score, depth) in KEPT_COMMENTS.items():
            m = mentions[cid]
            self.assertEqual(m["url"], f"{THREAD}comment/{cid}/")
            self.assertEqual(m["score"], score)
            self.assertEqual(m["depth"], depth)
            self.assertEqual(m["family"], "reddit")
            self.assertEqual(m["source_name"], "r/primeriatravel")
        self.assertTrue(mentions["tc0002"]["is_op"])
        self.assertEqual(mentions["tc0001"]["date"], "2026-02-10")

    def test_thread_urls_and_prefixed_ids_are_accepted_and_deduped(self):
        refs = ["https://www.reddit.com/r/primeriatravel/comments/tg0001/hotel_recommendations/", "t3_tg0001"]
        result = reddit_fetch.fetch_trees(fixture_backend(), refs)
        self.assertEqual(result["status"], "complete", result.get("reason"))
        self.assertEqual([t["id"] for t in result["threads"]], ["tg0001"])

    def test_output_never_contains_usernames(self):
        result = reddit_fetch.fetch_trees(fixture_backend(), ["tg0001"])
        text = json.dumps(result)
        self.assertNotIn("synthetic_", text)
        self.assertNotIn("author", text)
        self.assertIn("u/[user]", text)

    def test_mention_becomes_a_valid_ledger_mention(self):
        result = reddit_fetch.fetch_trees(fixture_backend(), ["tg0001"])
        mention = dict(tree_mentions(result)[0])
        mention["quote"] = "Hotel Alpha in the Old Town"
        candidate = {"name": "Hotel Alpha", "kind": "hotel", "mentions": [mention]}
        self.assertEqual(ledger.validate_candidate(candidate), [])

    def test_cli_tree_from_fixtures(self):
        code, out, err = cli("tree", "tg0001", "--fixtures", FIXTURES)
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["backend"], "arctic")
        self.assertEqual(len(tree_mentions(result)), 5)

    def test_later_thread_failure_gives_partial_and_stops(self):
        tree = json.loads((FIXTURES / "tree-tg0001.json").read_text(encoding="utf-8"))["response"]
        meta = json.loads((FIXTURES / "posts-ids-tg0001.json").read_text(encoding="utf-8"))["response"]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            record(folder, "ids.json", "posts/ids", {"ids": "tg0001,tg0009,tg0010"}, meta)
            record(folder, "t1.json", "comments/tree", {"link_id": "tg0001", "limit": 9999}, tree)
            record(folder, "t9.json", "comments/tree", {"link_id": "tg0009", "limit": 9999}, error="HTTP 503")
            result = reddit_fetch.fetch_trees(fixture_backend(folder), ["tg0001", "tg0009", "tg0010"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("503", result["reason"])
        self.assertEqual([t["id"] for t in result["threads"]], ["tg0001"])
        self.assertEqual([f["id"] for f in result["failed"]], ["tg0009", "tg0010"])

    def test_empty_thread_is_flagged_and_not_counted_as_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            record(folder, "ids.json", "posts/ids", {"ids": "tg0002"}, {"data": []})
            record(folder, "t2.json", "comments/tree", {"link_id": "tg0002", "limit": 9999}, {"data": []})
            result = reddit_fetch.fetch_trees(fixture_backend(folder), ["tg0002"])
        self.assertEqual(result["empty_threads"], ["tg0002"])
        self.assertEqual(result["threads_read"], 0)
        self.assertTrue(result["threads"][0]["empty"])


class FailureTest(unittest.TestCase):
    def unreachable_backend(self, waits):
        transport = reddit_fetch.HttpTransport(base="http://127.0.0.1:9/api", sleep=waits.append)
        return reddit_fetch.ArcticBackend(transport, sleep=lambda seconds: None)

    def test_unreachable_backend_reports_failed_not_empty_success(self):
        waits = []
        result = reddit_fetch.fetch_trees(self.unreachable_backend(waits), ["tg0001"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("unreachable", result["reason"])
        self.assertEqual(result["threads"], [])
        # the existing scripts' backoff: 5 tries, 5 s more each time, no wait after the last try
        self.assertEqual(waits, [5, 10, 15, 20])

    def test_unreachable_backend_fails_a_scan_too(self):
        result = reddit_fetch.scan(self.unreachable_backend([]), "primeriatravel", cities=["Testgrad"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("unreachable", result["reason"])
        self.assertEqual(result["posts"], [])

    def test_cli_missing_recording_exits_1_with_failed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = cli("tree", "tg0001", "--fixtures", tmp)
        self.assertEqual(code, 1, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "failed")
        self.assertIn("no recorded response", result["reason"])

    def test_sub_with_no_posts_at_all_fails(self):
        result = reddit_fetch.scan(fixture_backend(), "emptysub", cities=["Testgrad"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("r/emptysub", result["reason"])


class ScanTest(unittest.TestCase):
    def ids(self, result):
        return [p["id"] for p in result["posts"]]

    def test_scan_yields_only_posts_that_mention_the_city(self):
        result = reddit_fetch.scan(fixture_backend(), "primeriatravel", cities=["Testgrad"])
        self.assertEqual(result["status"], "complete", result.get("reason"))
        # sp0004 says "Testgradian" (not the city); sp0005 is upper case with an accent
        self.assertEqual(self.ids(result), ["sp0001", "sp0003", "sp0005", "sp0006"])
        self.assertEqual(result["scanned"], 6)
        for post in result["posts"]:
            self.assertEqual(post["url"], f"https://www.reddit.com/r/primeriatravel/comments/{post['id']}/")
            self.assertEqual(post["matched"], ["city"])
            self.assertIsInstance(post["score"], int)
        self.assertNotIn("synthetic_", json.dumps(result))

    def test_since_drops_older_posts(self):
        result = reddit_fetch.scan(fixture_backend(), "primeriatravel", cities=["Testgrad"], since="2023-01-01")
        self.assertEqual(self.ids(result), ["sp0001", "sp0003", "sp0005"])
        self.assertEqual(result["scanned"], 5)

    def test_query_matches_alongside_the_city(self):
        result = reddit_fetch.scan(fixture_backend(), "primeriatravel", cities=["Testgrad"], query="beach")
        self.assertEqual(self.ids(result), ["sp0001", "sp0002", "sp0003", "sp0005", "sp0006"])
        self.assertEqual(result["posts"][1]["matched"], ["query"])

    def test_backend_failure_after_first_page_gives_partial(self):
        base = 1781524800
        page = [{"id": f"bp{n:04d}", "subreddit": "bigsub", "title": f"Testgrad hotel {n}" if n % 2 else f"Other {n}",
                 "selftext": "", "score": 1, "num_comments": 0, "created_utc": base - n * 60} for n in range(100)]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            record(folder, "p1.json", "posts/search", {"subreddit": "bigsub", "limit": 100, "sort": "desc"},
                   {"data": page})
            record(folder, "p2.json", "posts/search",
                   {"subreddit": "bigsub", "limit": 100, "sort": "desc", "before": page[-1]["created_utc"]},
                   error="HTTP 503")
            result = reddit_fetch.scan(fixture_backend(folder), "bigsub", cities=["Testgrad"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("page 2", result["reason"])
        self.assertEqual(result["scanned"], 100)
        self.assertEqual(len(result["posts"]), 50)

    def test_cli_scan_writes_out_file_and_prints_a_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scan.json"
            code, stdout, err = cli("scan", "primeriatravel", "--city", "Testgrad", "--fixtures", FIXTURES,
                                    "--out", out)
            self.assertEqual(code, 0, err)
            saved = json.loads(out.read_text(encoding="utf-8"))
        summary = json.loads(stdout)
        self.assertEqual(saved["status"], "complete")
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["posts"], 4)

    def test_scan_needs_a_city_or_a_query(self):
        code, _, err = cli("scan", "primeriatravel", "--fixtures", FIXTURES)
        self.assertEqual(code, 2)
        self.assertIn("--city", err)


if __name__ == "__main__":
    unittest.main()
