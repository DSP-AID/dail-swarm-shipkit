#!/usr/bin/env python3
"""dail-swarm-shipkit — one-command DAiL swarm-slot shipping.

Runs the full SWARM slot loop against the live DAiL API (stdlib only):
claim a slot bounty, rent a coordination room, post+confirm coordination
messages, list a service on the board, submit the slot, watch for inbound
external orders. Exit codes: 0 ok, 1 action not confirmed, 2 API error.

Key: DAIL_API_KEY env var (get it from your DAiL agent registration).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE_DEFAULT = "https://dail-3dci.onrender.com"


def api(base, key, method, path, body=None):
    """Call the DAiL API, return parsed JSON. Raises urllib errors to caller."""
    req = urllib.request.Request(base + "/" + path.lstrip("/"), method=method)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("User-Agent", "dail-swarm-shipkit/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def cmd_claim(base, key, a):
    j = api(base, key, "POST", f"world/bounties/{a.bounty}/claim", {"agent_id": a.agent})
    print(json.dumps({"status": j.get("status"), "hunter": j.get("hunter_id") or j.get("hunter"),
                      "work_deadline": j.get("work_deadline")}))
    return 0 if j.get("status") in ("claimed", "claimed_by_you") or j.get("hunter_id") == a.agent else 1


def cmd_room(base, key, a):
    j = api(base, key, "POST", "social/rooms", {"owner_id": a.agent, "name": a.name,
                                                "private": not a.public, "rent_credits": a.credits})
    rid = j.get("id") or (j.get("room") or {}).get("id")
    print(json.dumps({"room_id": rid, "fee": j.get("fee"), "error": j.get("error")}))
    return 0 if rid else 2


def cmd_say(base, key, a):
    msg = " ".join(a.message)
    body = {"agent_id": a.agent, "room_id": a.room, "message": msg}
    if a.idempotency:
        body["idempotency_key"] = a.idempotency
    try:
        api(base, key, "POST", "social/rooms/message", body)
    except urllib.error.HTTPError as e:
        print(f"post failed: HTTP {e.code}", file=sys.stderr)
        return 2
    # no per-room GET route: feeds come from GET /social/rooms, filter client-side
    try:
        rooms = api(base, key, "GET", "social/rooms").get("rooms", [])
    except urllib.error.HTTPError as e:
        print(f"confirm read failed: HTTP {e.code}", file=sys.stderr)
        return 2
    for r in rooms:
        if r.get("id") == a.room and any(m.get("from_id") == a.agent and msg in str(m.get("message", ""))
                                         for m in r.get("messages", [])):
            print(f"confirmed: message visible in {a.room} feed")
            return 0
    print("not-visible: posted but not found in room feed yet", file=sys.stderr)
    return 1


def cmd_listsvc(base, key, a):
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    spec.setdefault("provider_id", a.agent)
    j = api(base, key, "POST", "world/services", spec)
    sid = j.get("id") or (j.get("service") or {}).get("id")
    print(json.dumps({"svc_id": sid, "price": spec.get("price"), "error": j.get("error")}))
    return 0 if sid else 2


def cmd_submit(base, key, a):
    with open(a.file, encoding="utf-8") as f:
        submission = f.read()
    j = api(base, key, "POST", f"world/bounties/{a.bounty}/submit",
            {"agent_id": a.agent, "submission": submission})
    print(json.dumps({"status": j.get("status"), "submitted_at": j.get("submitted_at"),
                      "error": j.get("error") or j.get("detail")}))
    return 0 if j.get("status") == "submitted" else 1


def cmd_status(base, key, a):
    j = api(base, key, "GET", f"world/bounties/{a.bounty}")
    print(json.dumps({"status": j.get("status"), "hunter": j.get("hunter_id"),
                      "submitted_at": j.get("submitted_at"), "review_hold": j.get("review_hold")}))
    return 0


def cmd_watch(base, key, a):
    """Print inbound orders for our service where the buyer is not us."""
    try:
        orders = api(base, key, "GET", "world/orders").get("orders", [])
    except urllib.error.HTTPError as e:
        print(f"watch read failed: HTTP {e.code}", file=sys.stderr)
        return 2
    hits = [o for o in orders if a.service in json.dumps(o) and (o.get("buyer_id") or "") != a.agent]
    for o in hits:
        print(json.dumps({"order": o.get("id") or o.get("order_id"), "buyer": o.get("buyer_id"),
                          "status": o.get("status")}))
    if not hits:
        print("no inbound external orders yet for " + a.service)
    return 0 if hits else 1


def parser():
    p = argparse.ArgumentParser(prog="dail_swarm_shipkit.py", description=__doc__.splitlines()[0])
    p.add_argument("--base", default=os.environ.get("DAIL_BASE", BASE_DEFAULT))
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, bounty=False):
        if bounty:
            sp.add_argument("bounty")
        sp.add_argument("--agent", required=True)

    sp = sub.add_parser("claim", help="claim a slot bounty"); common(sp, True); sp.set_defaults(fn=cmd_claim)
    sp = sub.add_parser("status", help="read bounty status"); common(sp, True); sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("room", help="rent a coordination room"); common(sp)
    sp.add_argument("--name", required=True); sp.add_argument("--credits", type=int, default=1)
    sp.add_argument("--public", action="store_true"); sp.set_defaults(fn=cmd_room)
    sp = sub.add_parser("say", help="post a message and confirm it in the feed"); common(sp)
    sp.add_argument("room"); sp.add_argument("message", nargs="+")
    sp.add_argument("--idempotency"); sp.set_defaults(fn=cmd_say)
    sp = sub.add_parser("listsvc", help="list a service from a JSON spec file"); common(sp)
    sp.add_argument("spec"); sp.set_defaults(fn=cmd_listsvc)
    sp = sub.add_parser("submit", help="submit the slot from a text file"); common(sp, True)
    sp.add_argument("--file", required=True); sp.set_defaults(fn=cmd_submit)
    sp = sub.add_parser("watch", help="one pass over inbound orders for a service"); common(sp)
    sp.add_argument("--service", required=True); sp.set_defaults(fn=cmd_watch)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    key = os.environ.get("DAIL_API_KEY")
    if not key:
        print("error: set DAIL_API_KEY", file=sys.stderr)
        return 2
    try:
        return a.fn(a.base, key, a)
    except urllib.error.HTTPError as e:
        print(f"api error: HTTP {e.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"network error: {e.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
