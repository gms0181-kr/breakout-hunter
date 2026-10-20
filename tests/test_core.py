import unittest
from hunter.core import *

class CoreTests(unittest.TestCase):
    def test_volume_excludes_current(self):
        bars=[{"volume":100} for _ in range(50)]+[{"volume":1000}]
        self.assertEqual(volume_metrics(bars)["ratios"]["50"],10)
    def test_missing_is_not_zero(self):
        s=engine_scores({})
        self.assertIsNone(s["score"])
        self.assertEqual(s["confidence"],0)
        self.assertEqual(len(s["missing"]),6)
    def test_reverse_split(self):
        out=adjusted_bars([{"time":"2026-08-01","open":1,"high":1,"low":1,"close":1,"volume":2500}],[{"date":"2026-09-01","old":25,"new":1}],"2026-10-01")
        self.assertEqual(out[0]["close"],25)
        self.assertEqual(out[0]["volume"],100)
    def test_future_split_not_applied(self):
        out=adjusted_bars([{"time":"2026-08-01","close":1}],[{"date":"2026-09-01","old":25,"new":1}],"2026-08-02")
        self.assertEqual(out[0]["close"],1)
    def test_outstanding_not_float(self):
        s=engine_scores({"outstanding":1000000,"volume":2000000})
        self.assertIsNone(s["scores"]["F"])
        self.assertEqual(s["rotation_basis"],"outstanding_proxy")
    def test_short_volume_not_interest(self):
        self.assertIsNone(engine_scores({"short":{"short_volume":1000000}})["scores"]["S"])
    def test_short_requires_verification(self):
        self.assertIsNone(engine_scores({"short":{"ctb":200,"available":0}})["scores"]["S"])
    def test_registration_not_issuance(self):
        self.assertIsNone(engine_scores({"sec":{"registered":10000000,"reviewed":False}})["scores"]["SEC"])
    def test_no_unproven_gap(self):
        self.assertIsNone(engine_scores({"sec":{"reviewed":True,"evidence":["url"],"as_of":"2026-10-01","immediately_sellable":False}})["scores"]["SEC"])
    def test_duplicate_security_not_added(self):
        events=[{"security_id":"W1","known_at":"2026-10-01","stage":"registered","shares":100},{"security_id":"W1","known_at":"2026-10-02","stage":"issued","shares":100}]
        self.assertEqual(len(deduplicate_supply(events,"2026-10-03")),1)
    def test_future_knowledge_excluded(self):
        self.assertEqual(point_in_time([{"known_at":"2026-10-20","time":"2026-10-10"}],"2026-10-19"),[])
    def test_scan_not_alphabetical_prefix(self):
        symbols=[f"T{i:04}" for i in range(1000)]
        order=scan_order(symbols,"2026-10-19")
        self.assertEqual(set(order),set(symbols))
        self.assertNotEqual(order[:20],sorted(symbols)[:20])
    def test_independent_engines(self):
        s=engine_scores({"float":1000000,"volume":3000000})
        self.assertTrue(s["scores"]["F"]>0)
        self.assertIsNone(s["scores"]["V"])
    def test_top10_independent_of_broker_orderability(self):
        def stock(i, orderable):
            return {"ticker":str(i),"toss_orderable":orderable,"bars":[{"volume":100} for _ in range(50)]+[{"volume":1000}]}
        for orderable in (None, False, True):
            items=[stock(i,orderable) for i in range(20)]
            top,_=rank(items)
            self.assertEqual(len(top),10)
            self.assertEqual([s["ticker"] for s in top],sorted(s["ticker"] for s in items)[:10])
            self.assertTrue(all(s["toss_orderable"] is orderable for s in top))
        top,_=rank([{"ticker":"EMPTY","toss_orderable":True}])
        self.assertEqual(top,[])
    def test_max_score(self):
        self.assertEqual(sum(WEIGHTS.values()),100)
    def test_hubc_claim_not_fixture_fact(self):
        import json
        from pathlib import Path
        fixture=json.loads(Path("tests/fixtures/hubc.json").read_text())
        self.assertEqual(fixture["status"],"unverified_claims")
        self.assertIsNone(fixture["expected_detection"])
    def test_missing_history_no_volume_ratio(self):
        self.assertIsNone(volume_metrics([{"volume":1}])["ratios"]["10"])

if __name__=="__main__": unittest.main()
