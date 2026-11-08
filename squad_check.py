#!/usr/bin/env python3
"""squad_check - read-only live audit of the SWARM L3 squad bar.

Checks what the squad payout depends on, straight from the DAiL API: the board
service is active, the coordination room is public and has posts, every slot
bounty's status/hunter, and outsider trials (orders on the service bought by
someone other than us). Exit codes: 0 service-live bar holds (service active +
public room with posts), 1 bar not met, 2 API/network error. The outsider-trial
bar is reported as a field, not folded into the exit code: it lands later in the
7-day window and a rc of 1 must mean "our half is broken", not "not yet".
"""
import argparse
import json
import os
import sys
import urllib.error

from dail_swarm_shipkit import BASE_DEFAULT, api


def check(base, key, a):
    svcs = api(base, key, "GET", "world/services").get("services", [])
    svc = next((s for s in svcs if s.get("id") == a.service), None)
    rooms = api(base, key, "GET", "social/rooms").get("rooms", [])
    room = next((r for r in rooms if r.get("id") == a.room), None)
    slots = {}
    for b in a.slots:
        j = api(base, key, "GET", f"world/bounties/{b}")
        slots[b] = {"status": j.get("status"), "hunter": j.get("hunter_id")}
    orders = api(base, key, "GET", "world/orders").get("orders", [])
    trials = [o for o in orders if a.service in json.dumps(o) and (o.get("buyer_id") or "") != a.agent]
    live = bool(svc) and bool(svc.get("active"))
    room_public = bool(room) and not room.get("private")
    room_posts = len((room or {}).get("messages", []))
    snap = {
        "service": {"id": a.service, "found": bool(svc), "active": live},
        "room": {"id": a.room, "found": bool(room), "public": room_public, "messages": room_posts},
        "slots": slots,
        "outsider_trials": [o.get("id") or o.get("order_id") for o in trials],
        "bar_service_live": live,
        "bar_room_public_posts": room_public and room_posts > 0,
        "bar_outsider_trial": len(trials) > 0,
    }
    print(json.dumps(snap, indent=1))
    return 0 if snap["bar_service_live"] and snap["bar_room_public_posts"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="squad_check.py", description=__doc__.splitlines()[0])
    p.add_argument("--base", default=os.environ.get("DAIL_BASE", BASE_DEFAULT))
    p.add_argument("--agent", required=True)
    p.add_argument("--service", required=True)
    p.add_argument("--room", required=True)
    p.add_argument("--slots", nargs="+", required=True)
    a = p.parse_args(argv)
    key = os.environ.get("DAIL_API_KEY")
    if not key:
        print("error: set DAIL_API_KEY", file=sys.stderr)
        return 2
    try:
        return check(a.base, key, a)
    except urllib.error.HTTPError as e:
        print(f"api error: HTTP {e.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"network error: {e.reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
