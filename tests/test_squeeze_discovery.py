import unittest,os
from unittest.mock import patch
from datetime import timedelta
from test_squeeze_hunter import fixture,NOW
from hunter.squeeze_signals import analyze,update_history
from hunter.squeeze_discovery import market_probe,select_borrow,select_intraday,early_signal
from hunter.squeeze_delivery import deliver

class DiscoveryTests(unittest.TestCase):
    def hot(self,ticker='X'):
        s,_=fixture();s['ticker']=ticker;s['bars'].append({**s['bars'][-1],'time':NOW.replace(hour=4).isoformat(),'available_at':NOW.isoformat(),'complete':False,'close':2,'open':1.2,'high':2.1,'low':1.1,'volume':20000});return s
    def test_unknown_short_enters_market_watch_without_fake_score(self):
        s=self.hot();a=analyze(s,{},NOW);self.assertTrue(a['candidate']);self.assertEqual(a['candidate_type'],'market_watch');self.assertIsNone(a['components']['short_pressure']['score']);self.assertIsNone(a['stage'])
    def test_partial_discovery_does_not_change_completed_scores(self):
        s=self.hot();a=analyze(s,{},NOW);s['bars'].pop();b=analyze(s,{},NOW);self.assertEqual(a['components'],b['components'])
    def test_future_discovery_rejected(self):
        s=self.hot();s['bars'][-1]['available_at']=(NOW+timedelta(minutes=1)).isoformat();self.assertFalse(market_probe(s,NOW)['triggered'])
    def test_old_bar_not_current_discovery(self):
        s=self.hot();s['bars'][-1]['time']=(NOW-timedelta(days=2)).isoformat();self.assertFalse(market_probe(s,NOW)['triggered'])
    def test_crashing_volume_is_not_watch(self):
        s=self.hot();s['bars'][-1].update(close=.5,low=.4,high=2.1);self.assertFalse(market_probe(s,NOW)['triggered'])
    def test_halt_blocks_market_candidate(self):
        s=self.hot();s['halt_status']='halted';self.assertFalse(analyze(s,{},NOW)['candidate'])
    def test_price_first_and_rotation_both_selected(self):
        stocks=[self.hot('HOT')]+[{'ticker':x} for x in ['A','B','C','D','E']];pre=[(s,analyze(s,{},NOW)) for s in stocks];chosen=select_intraday(pre,{},NOW,4);self.assertIn('HOT',[s['ticker'] for s in chosen]);self.assertEqual(len(chosen),4);self.assertIn('A',[s['ticker'] for s in chosen])
    def test_borrow_keeps_fair_quota(self):
        stocks=[{'ticker':x} for x in ['A','B','C','D']]+[self.hot('HOT')];self.assertEqual([s['ticker'] for s in select_borrow(stocks,{},NOW,4)][:2],['A','B']);self.assertIn('HOT',[s['ticker'] for s in select_borrow(stocks,{},NOW,4)])
    def test_rotated_intraday_avoids_prior_attempts(self):
        stocks=[({'ticker':x},{'signals':[]}) for x in ['A','B','C']];chosen=select_intraday(stocks,{'A':{'intraday_attempted_at':NOW.isoformat()}},NOW,1);self.assertEqual(chosen[0]['ticker'],'B')
    def test_intraday_invalidates_earlier_daily_probe(self):
        self.assertFalse(early_signal({'triggered':True},{'valid':True,'daily_change_pct':-5})['triggered'])
    def test_new_bar_duplicate_cooldown(self):
        s=self.hot();a=analyze(s,{},NOW);h=update_history({},[a],NOW);a['early_signal']['as_of']=(NOW+timedelta(minutes=5)).isoformat();h=update_history(h,[a],NOW+timedelta(minutes=5));self.assertEqual(len([x for x in h['alerts'] if x['kind']=='market_early_watch']),1)
    def test_delivery_unconfigured_is_explicit(self):
        with patch.dict(os.environ,{'SQUEEZE_ALERT_WEBHOOK_URL':''}):self.assertEqual(deliver([],{},NOW)['status'],'not_configured')
    def test_delivery_success_dedup_and_retry(self):
        class Response:
            status=204
            def __enter__(self):return self
            def __exit__(self,*args):pass
        a={'id':'X|market|1','ticker':'X','occurred_at':NOW.isoformat()};calls=[]
        def send(req,timeout):calls.append(req);return Response()
        with patch.dict(os.environ,{'SQUEEZE_ALERT_WEBHOOK_URL':'https://example.com/hook'}):
            d=deliver([a],{},NOW,send);self.assertEqual(d['accepted_this_run'],1);d=deliver([a],d,NOW,send);self.assertEqual(len(calls),1)
            d=deliver([{**a,'id':'different'}],d,NOW,lambda *a,**k:(_ for _ in ()).throw(RuntimeError('secret')));self.assertEqual(d['failed_this_run'],1);self.assertNotIn('secret',str(d));self.assertNotIn('different',d['accepted_ids'])
    def test_delivery_no_historical_backlog(self):
        with patch.dict(os.environ,{'SQUEEZE_ALERT_WEBHOOK_URL':'https://example.com/hook'}):
            d=deliver([{'id':'old','occurred_at':(NOW-timedelta(days=1)).isoformat()}],{},NOW,lambda *a,**k:self.fail('old alert sent'));self.assertEqual(d['accepted_this_run'],0)
