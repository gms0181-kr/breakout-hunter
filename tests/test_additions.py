import unittest
from hunter.core import engine_scores
from hunter.sec import PATTERNS
import re
class AdditionalTests(unittest.TestCase):
    def test_ctb_independent(self):
        s=engine_scores({"short":{"ctb":150,"cross_verified":True,"as_of":"2026-10-20"}})
        self.assertEqual(s["scores"]["S"],6)
        self.assertEqual(s["confidence"],6)
        self.assertTrue(s["candidate"])
    def test_short_zero_not_squeeze_certification(self):
        s=engine_scores({"short":{"available":0,"cross_verified":True,"as_of":"2026-10-20"}})
        self.assertEqual(s["scores"]["S"],4)
        self.assertNotIn("short_cover_confirmed",s)
    def test_sec_detection_not_free_sale(self):
        flags=[k for k,v in PATTERNS.items() if re.search(v,"pre-funded warrants resale 9.99% ownership",re.I)]
        self.assertIn("PRE_FUNDED",flags)
        self.assertIn("BLOCKER_9_99",flags)
        self.assertIsNone(engine_scores({"sec":{"risk_flags":flags,"reviewed":False}})["scores"]["SEC"])
