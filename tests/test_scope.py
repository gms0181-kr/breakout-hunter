import unittest
from hunter.scope import in_scope,security_reason,filter_report
class ScopeTests(unittest.TestCase):
    def test_real_funds_removed_even_with_small_market_cap(self):
        for name in ['RiverNorth Flexible Municipal Income Fund','Eaton Vance Senior Floating Rate Trust','Clough Global Dividend and Income Fund','Invesco Value Municipal Income Trust','Treasury Bond ETF','Company Preferred Stock','Company 6% Notes','Company REIT','Acquisition Corporation - Common Stock']:
            self.assertFalse(in_scope({'name':name,'price':1,'market_cap':100000000}),name)
    def test_company_and_ads_and_bank_are_retained(self):
        for name in ['INLIF Limited - Ordinary Shares','Achieve Life Sciences, Inc. - Common Shares','Example Dividend Technologies Inc. - Common Stock','Acme Bank & Trust - Common Stock','Example Limited - American Depositary Shares']:
            self.assertTrue(in_scope({'name':name,'price':1,'market_cap':100000000}),name)
    def test_cap_hard_limit_and_missing(self):
        for cap in [None,0,-1,2000000001,float('nan'),True]:
            self.assertFalse(in_scope({'name':'Company Inc.','price':1,'market_cap':cap}))
        self.assertTrue(in_scope({'name':'Company Inc.','price':1,'market_cap':2000000000}))
        self.assertFalse(in_scope({'name':'Company Inc.','price':1,'market_cap':3000000000},10000000000))
    def test_all_lists_including_historical_are_filtered(self):
        good={'name':'Company Inc.','price':1,'market_cap':100000000}
        bad={'name':'Municipal Fund','price':1,'market_cap':100000000}
        r={k:[good,bad] for k in ['top10','last_top10','research_top10','watchlist','verification_candidates']}
        filter_report(r)
        for k in ['top10','last_top10','research_top10','watchlist','verification_candidates']:self.assertEqual(r[k],[good])
    def test_explicit_product_type(self):
        self.assertIsNotNone(security_reason({'name':'Unknown','etf':True}))
