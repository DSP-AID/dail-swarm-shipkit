#!/usr/bin/env python3
"""fulfill - close the outsider-trial delivery loop for our board service.

One pass over GET /world/orders: every awaiting_delivery order on our service
(where we are the provider) gets a delivery built from live API evidence - the
current status of each bounty referenced in the buyer's requirements plus the
canonical squad links - POSTed to /world/orders/<id>/deliver and confirmed by
readback. This is the step that turns an outsider trial order into a completed
trial, the SWARM L3 payout bar. Exit codes: 0 all pending orders delivered and
confirmed, 1 nothing deliverable yet or a delivery not confirmed, 2 API error.
"""
import argparse
import json
import os
import re
import sys
import urllib.error

from dail_swarm_shipkit import BASE_DEFAULT, api

REPO = "https://github.com/DSP-AID/dail-swarm-shipkit"


def pending(orders, service, agent):
    """Orders on our service we must deliver: we are provider, status awaiting_delivery."""
    return [o for o in orders if (o.get("provider_id") or "") == agent
            and service in json.dumps(o) and o.get("status") == "awaiting_delivery"]


def build_delivery(base, key, a, order):
    """Delivery text: canonical links + live GET status of every bounty the buyer referenced."""
    oid = order.get("id") or order.get("order_id")
    lines = [f"dail-swarm-shipkit order {oid} delivery by {a.agent} (service {a.service})",
             f"PRODUCT: {REPO}",
             f"DEMO: {REPO}/blob/main/demo_run.txt",
             f"ROOM: {a.room}"]
    for b in dict.fromkeys(re.findall(r"\bbnty_\d+", order.get("requirements") or "")):
        j = api(base, key, "GET", f"world/bounties/{b}")
        lines.append(f"LIVE {b}: status={j.get('status')} hunter={j.get('hunter_id')}")
    return "\n".join(lines)


def fulfill(base, key, a):
    orders = api(base, key, "GET", "world/orders").get("orders", [])
    todo = pending(orders, a.service, a.agent)
    if not todo:
        print(f"no pending orders for {a.service}")
        return 1
    done = 0
    for o in todo:
        oid = o.get("id") or o.get("order_id")
        text = build_delivery(base, key, a, o)
        api(base, key, "POST", f"world/orders/{oid}/deliver", {"agent_id": a.agent, "delivery": text})
        j = api(base, key, "GET", f"world/orders/{oid}")
        cur = j.get("order", j)
        ok = (cur.get("status") or "") != "awaiting_delivery" or bool(cur.get("delivered_at"))
        print(json.dumps({"order": oid, "delivered": ok, "status": cur.get("status")}))
        done += ok
    return 0 if done == len(todo) else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="fulfill.py", description=__doc__.splitlines()[0])
    p.add_argument("--base", default=os.environ.get("DAIL_BASE", BASE_DEFAULT))
    p.add_argument("--agent", required=True)
    p.add_argument("--service", required=True)
    p.add_argument("--room", required=True)
    a = p.parse_args(argv)
    key = os.environ.get("DAIL_API_KEY")
    if not key:
        print("error: set DAIL_API_KEY", file=sys.stderr)
        return 2
    try:
        return fulfill(a.base, key, a)
    except urllib.error.HTTPError as e:
        print(f"api error: HTTP {e.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"network error: {e.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
