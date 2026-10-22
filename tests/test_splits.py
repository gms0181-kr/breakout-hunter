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
