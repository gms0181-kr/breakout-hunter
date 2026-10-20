import unittest
from hunter.float_ctb import number,overview,finviz,borrow,combine_float,apply_cached
class FloatBorrowTests(unittest.TestCase):
    def test_units_and_missing(self):
        for raw,value in (("15.04M",15040000),("178,822",178822),("2.1B",2100000000),("5K",5000)):
            self.assertEqual(number(raw),value)
        for raw in ("-","N/A","","0","12%"):self.assertIsNone(number(raw))
    def test_float_is_not_outstanding_or_short_float(self):
        html="<title>TEST Stock</title><div>Shares Out</div><div>20M</div><div>Float</div><div>15M</div><div>Short Interest %</div><div>10%</div>"
        item=overview(html,"TEST")
        self.assertEqual(item["value"],15000000)
        self.assertEqual(item["outstanding_reference"],20000000)
        self.assertIsNone(item["source_as_of"])
        self.assertTrue(item["approximate"])
    def test_finviz_exact_share_label(self):
        self.assertEqual(finviz("<title>TEST</title>Short Float 20% Shs Float 5.2M","TEST")["value"],5200000)
    def test_wrong_symbol_and_impossible_float(self):
        with self.assertRaises(ValueError):overview("<title>OTHER</title>Float 1M","TEST")
        with self.assertRaises(ValueError):overview("<title>TEST</title>Float 30M Shares Out 20M","TEST")
    def test_borrow_percent_zero_availability_and_timezone(self):
        html="<title>TEST Borrow Fee</title>As of <b>2026-10-20 03:38:57 PM EDT</b>, there were <b>0</b> shares available with a fee of <b>3.89<!-- -->%</b>."
        item=borrow(html,"TEST")
        self.assertEqual(item["ctb"],3.89)
        self.assertEqual(item["available"],0)
        self.assertEqual(item["as_of"],"2026-10-20T19:38:57+00:00")
        self.assertFalse(item["cross_verified"])
    def test_missing_borrow_is_not_zero(self):
        self.assertIsNone(borrow("<title>TEST</title>No data","TEST")["available"])
    def test_float_disagreement_is_exposed(self):
        item=combine_float([{"value":1000000},{"value":10000000}])
        self.assertEqual(item["status"],"conflict")
        self.assertIsNone(item["display_value"])
        self.assertEqual(len(item["sources"]),2)
    def test_matching_or_single_source(self):
        self.assertEqual(combine_float([{"value":1000000},{"value":1020000}])["status"],"matched")
        self.assertEqual(combine_float([{"value":1000000},{"error":"HTTP 403"}])["status"],"single_source")
    def test_only_matched_basis_enters_float_score(self):
        for state,flags,expected in (("matched",[],1000000),("single_source",[],None),("conflict",[],None),("matched",["ADS"],None)):
            stocks=[{"ticker":"TEST"}]
            apply_cached(stocks,{"symbols":{"TEST":{"float":{"status":state,"display_value":1000000,"flags":flags},"borrow":{"ctb":30,"available":0,"cross_verified":False}}}})
            self.assertEqual(stocks[0]["float"],expected)
            self.assertFalse(stocks[0]["short"]["cross_verified"])
if __name__=="__main__":unittest.main()
