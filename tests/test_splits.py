import os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import AsyncMock,patch
from hunter.scope import scope_reason,recent_reverse_split
from hunter.splits import snapshot,apply
NOW=datetime(2026,10,22,16,tzinfo=timezone.utc)
class SplitPolicyTests(unittest.TestCase):
    def test_price_boundary_missing_and_recent_trade(self):
        s={'name':'Company Inc.','market_cap':1000000,'price':9.99}
        self.assertIsNone(scope_reason(s))
        self.assertEqual(scope_reason({**s,'price':10}),'price_at_or_above_10')
        self.assertEqual(scope_reason({**s,'price':None}),'price_unverified')
        self.assertEqual(scope_reason({**s,'halt_check':{'trade_price':10.5}}),'price_at_or_above_10')
        self.assertIsNone(scope_reason({**s,'price':None},include_trading=False))
    def test_reverse_split_window_and_future(self):
        for days,want in [(0,True),(30,True),(31,False),(-1,False)]:
            stock={'split_check':{'events':[{'ex_date':(NOW-timedelta(days=days)).date().isoformat()}]}}
            self.assertEqual(recent_reverse_split(stock,NOW),want)
    def test_forward_split_not_excluded_and_reverse_ratio_is(self):
        for ratio,want in [('1-for-10',True),('10-for-1',False)]:
            stock={'enrichment':{'float':{'sources':[{'last_split_date':'2026-10-20','last_split':ratio}]}}}
            self.assertEqual(recent_reverse_split(stock,NOW),want)
    def test_recent_reverse_split_is_price_exception_not_exclusion(self):
        base={'name':'Company Inc.','market_cap':1000000}
        for price in (1,9.99,10,30):
            for days,allowed in ((0,True),(30,True),(31,price<10),(-1,price<10)):
                stock={**base,'price':price,'split_check':{'events':[{'ex_date':(NOW-timedelta(days=days)).date().isoformat()}]}}
                self.assertEqual(scope_reason(stock,now=NOW) is None,allowed,(price,days))
    def test_cached_reverse_split_allows_high_trade_price(self):
        stock={'name':'Company Inc.','market_cap':1000000,'price':9,'halt_check':{'trade_price':30},'enrichment':{'float':{'sources':[{'last_split_date':'2026-10-20','last_split':'1-for-30 (reverse)'}]}}}
        self.assertIsNone(scope_reason(stock,now=NOW))
        stock['enrichment']['float']['sources'][0]['last_split']='30-for-1'
        self.assertEqual(scope_reason(stock,now=NOW),'price_at_or_above_10')
    def test_reverse_split_does_not_override_security_or_cap(self):
        stock={'name':'Company Inc.','price':30,'market_cap':3000000000,'split_check':{'events':[{'ex_date':'2026-10-20'}]}}
        self.assertEqual(scope_reason(stock,now=NOW),'above_smallcap_limit')
        stock.update(name='Company ETF',market_cap=1000000)
        self.assertEqual(scope_reason(stock,now=NOW),'fund_or_non_common_security')
    def test_symbol_change_matches_both_symbols(self):
        stocks=[{'ticker':'OLD'},{'ticker':'NEW'},{'ticker':'OTHER'}]
        apply(stocks,{'status':'ok','events':[{'symbol':'OLD','new_symbol':'NEW','ex_date':'2026-10-20'}]})
        self.assertEqual([len(s['split_check']['events']) for s in stocks],[1,1,0])
class SplitFeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_pagination_retained_and_failure_not_clean(self):
        fetch=AsyncMock(side_effect=[{'corporate_actions':{'reverse_splits':[{'symbol':'A','ex_date':'2026-10-20'}]},'next_page_token':'page2'},{'corporate_actions':{'reverse_splits':[]}}])
        with patch.dict(os.environ,{'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'}):r=await snapshot(None,fetch)
        self.assertEqual(r['status'],'ok');self.assertEqual(len(r['events']),1);self.assertEqual(fetch.await_count,2)
        with patch.dict(os.environ,{'ALPACA_API_KEY':'fixture','ALPACA_API_SECRET':'fixture'}):r=await snapshot(None,AsyncMock(return_value={}))
        self.assertEqual(r['status'],'unverified');self.assertIn('payload',r['error'])
