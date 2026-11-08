import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import resubmit as rs
from test_dail_swarm_shipkit import fake_urlopen, http_error  # shared urlopen mock

ARGS = ["bnty_5", "--agent", "me", "--service", "svc_1", "--room", "room_1"]


def orders(with_trial=True):
    o = [{"orders": []}]
    if with_trial:
        o = [{"orders": [{"id": "ord_1", "order_id": "ord_1", "provider_id": "me",
                          "buyer_id": "other", "service_id": "svc_1", "status": "delivered"}]}]
    return o


def run(argv, responses):
    with mock.patch.object(rs.urllib.request, "urlopen", fake_urlopen(responses)):
        return rs.main(["--base", "https://x.test"] + argv)


class TestResubmit:
    def test_trial_evidence_and_confirm_exit0(self):
        # orders -> trial readback -> resubmit POST -> bounty readback
        resp = orders() + [{"order": {"id": "ord_1", "status": "delivered",
                                      "delivered_at": "2026-11-08T20:17Z", "confirmed_at": None}},
                           {}, {"resubmitted_at": "2026-11-08T20:30Z", "resubmission_status": "pending"}]
        m = fake_urlopen(resp)
        with mock.patch.object(rs.urllib.request, "urlopen", m):
            assert rs.main(["--base", "https://x.test"] + ARGS) == 0
        post = next(c for c in m.calls if c[0] == "POST")
        assert "/world/bounties/bnty_5/resubmit" in post[1]
        assert b"TRIAL ord_1: buyer=other status=delivered" in post[2]
        assert b"room_1" in post[2]

    def test_no_trials_still_resubmits_exit0(self):
        resp = orders(with_trial=False) + [{}, {"resubmitted_at": "2026-11-08T20:30Z"}]
        m = fake_urlopen(resp)
        with mock.patch.object(rs.urllib.request, "urlopen", m):
            assert rs.main(["--base", "https://x.test"] + ARGS) == 0
        post = next(c for c in m.calls if c[0] == "POST")
        assert b"TRIAL" not in post[2]

    def test_readback_not_confirmed_exit1(self):
        resp = orders(with_trial=False) + [{}, {"resubmitted_at": None}]
        assert run(ARGS, resp) == 1

    def test_review_hold_gate_exit1(self):
        # 400 "not on review hold" is a state (rc 1), not an API error (rc 2)
        body = b'{"detail":"bounty is not on review hold; resubmission opens only under a review hold"}'
        assert run(ARGS, orders(with_trial=False) + [http_error(400, body)]) == 1

    def test_api_error_exit2(self):
        assert run(ARGS, [http_error(500)]) == 2
