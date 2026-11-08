import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import fulfill as fl
from test_dail_swarm_shipkit import fake_urlopen, http_error  # shared urlopen mock

ARGS = ["--agent", "me", "--service", "svc_1", "--room", "room_1"]


def order(status="awaiting_delivery"):
    return [{"orders": [{"id": "ord_1", "order_id": "ord_1", "provider_id": "me",
                         "buyer_id": "other", "service_id": "svc_1", "status": status,
                         "requirements": "run the loop for bnty_9 in room_1"}]}]


def run(argv, responses):
    with mock.patch.object(fl.urllib.request, "urlopen", fake_urlopen(responses)):
        return fl.main(["--base", "https://x.test"] + argv)


class TestFulfill:
    def test_no_pending_exit1(self):
        assert run(ARGS, order(status="completed")) == 1

    def test_delivers_and_confirms_exit0(self):
        # orders -> bounty live status -> deliver POST -> readback GET
        resp = order() + [{"status": "submitted", "hunter_id": "other"}, {},
                          {"order": {"id": "ord_1", "status": "delivered"}}]
        m = fake_urlopen(resp)
        with mock.patch.object(fl.urllib.request, "urlopen", m):
            assert fl.main(["--base", "https://x.test"] + ARGS) == 0
        post = next(c for c in m.calls if c[0] == "POST")
        assert "/world/orders/ord_1/deliver" in post[1]
        assert b"bnty_9" in post[2]  # buyer-referenced bounty status embedded in delivery

    def test_readback_not_confirmed_exit1(self):
        resp = order() + [{"status": "open", "hunter_id": None}, {},
                          {"order": {"id": "ord_1", "status": "awaiting_delivery"}}]
        assert run(ARGS, resp) == 1

    def test_api_error_exit2(self):
        assert run(ARGS, order() + [http_error(500)]) == 2
