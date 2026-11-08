import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

os.environ["DAIL_API_KEY"] = "test-key"
sys.path.insert(0, os.path.dirname(__file__))
import dail_swarm_shipkit as sk


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(responses):
    """Return an urlopen mock; responses is a list of dicts or HTTPError raised in order."""
    calls = []

    def _open(req, timeout=None):
        calls.append((req.get_method(), req.full_url, req.data))
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return Resp(json.dumps(r).encode())

    _open.calls = calls
    return _open


def run(argv, responses, monkeypatch=True):
    with mock.patch.object(sk.urllib.request, "urlopen", fake_urlopen(responses)):
        code = sk.main(["--base", "https://x.test"] + argv)
    return code


def http_error(code=403):
    return urllib.error.HTTPError("https://x.test", code, "nope", {}, io.BytesIO(b"{}"))


class TestShipkit(unittest.TestCase):
    def test_claim_ok(self):
        c = run(["claim", "bnty_1", "--agent", "me"],
                [{"status": "claimed", "hunter_id": "me", "work_deadline": "d"}])
        self.assertEqual(c, 0)

    def test_claim_rejected(self):
        c = run(["claim", "bnty_1", "--agent", "me"],
                [{"status": "failed", "error": "already claimed"}])
        self.assertEqual(c, 1)

    def test_room_returns_id(self):
        with mock.patch.object(sk.urllib.request, "urlopen",
                               fake_urlopen([{"id": "room_0042", "fee": 1}])):
            code = sk.main(["--base", "https://x.test", "room", "--agent", "me",
                            "--name", "R", "--public"])
        self.assertEqual(code, 0)

    def test_say_confirmed(self):
        feed = {"rooms": [{"id": "room_1", "messages": [
            {"from_id": "me", "message": "hello world"}]}]}
        c = run(["say", "room_1", "hello", "world", "--agent", "me"], [{}, feed])
        self.assertEqual(c, 0)

    def test_say_not_visible(self):
        feed = {"rooms": [{"id": "room_1", "messages": []}]}
        c = run(["say", "room_1", "hello", "--agent", "me"], [{}, feed])
        self.assertEqual(c, 1)

    def test_post_http_error_exit2(self):
        c = run(["say", "room_1", "hello", "--agent", "me"], [http_error(403)])
        self.assertEqual(c, 2)

    def test_listsvc_posts_spec(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"name": "N", "price": 3}, f)
            path = f.name
        try:
            opener = fake_urlopen([{"id": "svc_0300"}])
            with mock.patch.object(sk.urllib.request, "urlopen", opener):
                code = sk.main(["--base", "https://x.test", "listsvc", path, "--agent", "me"])
            body = json.loads(opener.calls[0][2])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        self.assertEqual(body["provider_id"], "me")
        self.assertEqual(body["price"], 3)

    def test_submit_reads_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("my submission text")
            path = f.name
        try:
            opener = fake_urlopen([{"status": "submitted", "submitted_at": "t"}])
            with mock.patch.object(sk.urllib.request, "urlopen", opener):
                code = sk.main(["--base", "https://x.test", "submit", "bnty_1",
                                "--file", path, "--agent", "me"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(opener.calls[0][2])["submission"], "my submission text")

    def test_watch_finds_external_buyer(self):
        orders = {"orders": [{"id": "ord_1", "buyer_id": "other", "detail": "svc_0300"},
                             {"id": "ord_2", "buyer_id": "me", "detail": "svc_0300"}]}
        c = run(["watch", "--agent", "me", "--service", "svc_0300"], [orders])
        self.assertEqual(c, 0)

    def test_watch_none_found(self):
        c = run(["watch", "--agent", "me", "--service", "svc_0300"], [{"orders": []}])
        self.assertEqual(c, 1)


if __name__ == "__main__":
    unittest.main()
