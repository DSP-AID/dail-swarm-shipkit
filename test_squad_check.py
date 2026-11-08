import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import squad_check as sc
from test_dail_swarm_shipkit import fake_urlopen, http_error  # shared urlopen mock

SLOTS = ["bnty_1", "bnty_2"]


def snap(service_active=True, room_private=False, posts=1, trials=("other",)):
    """Response list in the order check() calls the API: services, rooms, slots, orders."""
    return [
        {"services": [{"id": "svc_1", "active": service_active}]},
        {"rooms": [{"id": "room_1", "private": room_private,
                    "messages": [{"from_id": "x"}] * posts}]},
        {"status": "submitted", "hunter_id": "me"},
        {"status": "open", "hunter_id": None},
        {"orders": [{"id": f"ord_{i}", "buyer_id": b, "detail": "svc_1"}
                    for i, b in enumerate(trials)]},
    ]


def run(argv, responses):
    with mock.patch.object(sc.urllib.request, "urlopen", fake_urlopen(responses)):
        return sc.main(["--base", "https://x.test"] + argv)


ARGS = ["--agent", "me", "--service", "svc_1", "--room", "room_1", "--slots"] + SLOTS


class TestSquadCheck:
    def test_bar_holds_exit0(self):
        assert run(ARGS, snap()) == 0

    def test_service_inactive_exit1(self):
        assert run(ARGS, snap(service_active=False)) == 1

    def test_room_private_exit1(self):
        assert run(ARGS, snap(room_private=True)) == 1

    def test_no_trial_still_exit0_but_reported(self):
        assert run(ARGS, snap(trials=())) == 0

    def test_api_error_exit2(self):
        assert run(ARGS, [http_error(403)]) == 2
