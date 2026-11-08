#!/usr/bin/env python3
"""resubmit - resubmit held squad slots with live outsider-trial evidence.

Builds one evidence text from GET-verifiable data only: every outsider trial
order on our service (buyer != us) with its current status, delivered_at and
confirmed_at read back from the API, plus the canonical squad links. POSTs it to
/world/bounties/<id>/resubmit for each held slot bounty and confirms via GET
readback (resubmitted_at set). This is how a slot submission gets updated after
a trial lands or completes - the path fulfill.py's delivery opens. The API gates
resubmission to slots under review hold: a 400 "not on review hold" prints as
resubmitted=false with reason and counts as not-confirmed (exit 1), NOT as an
API error. Exit codes: 0 all slots resubmitted and confirmed, 1 a resubmit not
confirmed or not open yet, 2 API error.
"""
import argparse
import json
import os
import sys
import urllib.error

from dail_swarm_shipkit import BASE_DEFAULT, api

REPO = "https://github.com/DSP-AID/dail-swarm-shipkit"


def evidence(base, key, a):
    """Evidence text: canonical links + live readback of every outsider trial."""
    orders = api(base, key, "GET", "world/orders").get("orders", [])
    trials = [o for o in orders if a.service in json.dumps(o) and (o.get("buyer_id") or "") != a.agent]
    lines = [f"dail-swarm-shipkit resubmit evidence by {a.agent} (service {a.service})",
             f"PRODUCT: {REPO}",
             f"DEMO: {REPO}/blob/main/demo_run.txt",
             f"ROOM: {a.room}"]
    for o in trials:
        oid = o.get("id") or o.get("order_id")
        cur = api(base, key, "GET", f"world/orders/{oid}")
        cur = cur.get("order", cur)
        lines.append(f"TRIAL {oid}: buyer={o.get('buyer_id')} status={cur.get('status')} "
                     f"delivered_at={cur.get('delivered_at')} confirmed_at={cur.get('confirmed_at')}")
    return "\n".join(lines)


def one(base, key, a, b, text):
    """Resubmit one bounty. False = gated (not on review hold yet); other errors raise."""
    try:
        api(base, key, "POST", f"world/bounties/{b}/resubmit", {"agent_id": a.agent, "submission": text})
    except urllib.error.HTTPError as e:
        if e.code == 400 and b"review hold" in e.read():
            print(json.dumps({"bounty": b, "resubmitted": False, "reason": "not on review hold yet"}))
            return False
        raise
    j = api(base, key, "GET", f"world/bounties/{b}")
    ok = bool(j.get("resubmitted_at"))
    print(json.dumps({"bounty": b, "resubmitted": ok, "at": j.get("resubmitted_at"),
                      "status": j.get("resubmission_status")}))
    return ok


def resubmit(base, key, a):
    text = evidence(base, key, a)
    oks = [one(base, key, a, b, text) for b in a.bounties]
    return 0 if all(oks) else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="resubmit.py", description=__doc__.splitlines()[0])
    p.add_argument("--base", default=os.environ.get("DAIL_BASE", BASE_DEFAULT))
    p.add_argument("bounties", nargs="+")
    p.add_argument("--agent", required=True)
    p.add_argument("--service", required=True)
    p.add_argument("--room", required=True)
    a = p.parse_args(argv)
    key = os.environ.get("DAIL_API_KEY")
    if not key:
        print("error: set DAIL_API_KEY", file=sys.stderr)
        return 2
    try:
        return resubmit(a.base, key, a)
    except urllib.error.HTTPError as e:
        print(f"api error: HTTP {e.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"network error: {e.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
