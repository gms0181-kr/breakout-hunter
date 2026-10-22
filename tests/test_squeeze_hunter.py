import unittest
from datetime import datetime,timedelta,timezone
from copy import deepcopy
from hunter.squeeze_signals import analyze,ctb_metrics,classify,update_history,safe_bars,WEIGHTS
from hunter.squeeze_scan import due_targets,merge_observation,replay,session_state
NOW=datetime(2026,10,22,18,tzinfo=timezone.utc)
def fixture():
    bars=[]
    for i in range(65):
        t=NOW-timedelta(days=65-i)
        bars.append({'time':t.isoformat(),'open':1,'high':1.05,'low':.95,'close':1,'volume':1000,'vwap':1.01,'available_at':NOW.isoformat(),'complete':True})
    bars[-1].update(open=1.01,high=1.23,low=1.0,close=1.2,volume=6000,vwap=1.1)
    s={'ticker':'TEST','bars':bars,'sec':{},'halt_status':'no_halt_detected'}
    b={'ctb':100,'available':0,'as_of':NOW.isoformat(),'observed_at':NOW.isoformat(),'source':'https://chartexchange.com/symbol/nasdaq-test/borrow-fee/','lender':'Interactive Brokers'}
    h=[{**b,'ctb':30,'available':100000,'as_of':(NOW-timedelta(days=1)).isoformat(),'observed_at':(NOW-timedelta(days=1)).isoformat()}]
    o={'borrow':b,'borrow_history':h,'short_interest':{'official_origin':'FINRA','source':'https://chartexchange.com/symbol/nasdaq-test/short-interest/','observed_at':NOW.isoformat(),'settlement_date':'2026-09-30','shares':100000,'float_pct':25,'change_pct':25}}
    return s,o
class IndependentHunterTests(unittest.TestCase):
    def test_weights(self):self.assertEqual(sum(WEIGHTS.values()),100)
    def test_missing_is_not_zero(self):
        a=analyze({'ticker':'X'},{},NOW);self.assertIsNone(a['observed_score']);self.assertEqual(a['coverage'],0);self.assertIsNone(a['stage']);self.assertFalse(a['candidate'])
    def test_known_score_no_renormalization(self):
        s,o=fixture();a=analyze(s,o,NOW);self.assertLessEqual(a['observed_score'],a['coverage']);self.assertIsNone(a['total_score']);self.assertEqual(a['components']['dilution_gap']['score'],None);self.assertTrue(a['candidate'])
    def test_ctb_window_baselines(self):
        s,o=fixture();b=ctb_metrics(o,NOW);self.assertAlmostEqual(b['24h_change_pct'],233.3333333333);self.assertIsNone(b['3d_change_pct']);self.assertEqual(b['available_drop_pct'],100)
    def test_not_fake_zero_duration(self):
        s,o=fixture();self.assertIsNone(ctb_metrics(o,NOW)['zero_observed_hours'])
    def test_resupply(self):
        s,o=fixture();o['borrow_history'][0]['available']=0;o['borrow']['available']=1000;self.assertTrue(ctb_metrics(o,NOW)['resupplied']);self.assertIsNone(ctb_metrics(o,NOW)['available_drop_pct'])
    def test_future_borrow(self):
        s,o=fixture();o['borrow']['as_of']=(NOW+timedelta(hours=1)).isoformat();self.assertFalse(ctb_metrics(o,NOW)['valid'])
    def test_stale_borrow(self):
        s,o=fixture();o['borrow']['stale']=True;self.assertFalse(ctb_metrics(o,NOW)['valid'])
    def test_unknown_source_not_scored(self):
        s,o=fixture();o['borrow']['lender']='unknown';self.assertFalse(ctb_metrics(o,NOW)['valid'])
    def test_future_partial_bar(self):
        s,o=fixture();s['bars'][-1]['complete']=False;self.assertEqual(len(safe_bars(s['bars'],NOW)),64);s['bars'][-2]['available_at']=(NOW+timedelta(days=1)).isoformat();self.assertEqual(len(safe_bars(s['bars'],NOW)),63)
    def test_crash_volume_not_inflow(self):
        s,o=fixture();s['bars'][-1].update(open=1,high=1.1,low=.4,close=.45,volume=50000);a=analyze(s,o,NOW);self.assertEqual(a['components']['capital_inflow']['score'],0)
    def test_split_ratio_si_block(self):
        s,o=fixture();o['short_interest']['float_pct']=120;a=analyze(s,o,NOW);self.assertFalse(a['official_interest']['scoring_valid'])
    def test_future_si_observation(self):
        s,o=fixture();o['short_interest']['observed_at']=(NOW+timedelta(days=1)).isoformat();self.assertFalse(analyze(s,o,NOW)['official_interest']['scoring_valid'])
    def test_lexical_no_safe_dilution(self):
        s,o=fixture();s['sec']={'risk_flags':[],'documents':[{'sha256':'abc','known_at':NOW.isoformat()}]};self.assertEqual(analyze(s,o,NOW)['dilution']['status'],'추가 검증 필요')
    def test_high_risk_review(self):
        s,o=fixture();s['sec']={'squeeze_assessment':{'reviewed':True,'contracts_reconciled':True,'source':'https://www.sec.gov/Archives/example','reviewed_at':NOW.isoformat(),'known_at':NOW.isoformat(),'status':'즉시 출회 위험 높음'}};a=analyze(s,o,NOW);self.assertTrue(a['high_risk']);self.assertEqual(a['components']['dilution_gap']['score'],0)
    def test_stage_jump_and_downgrade(self):
        s,o=fixture();a=analyze(s,o,NOW);self.assertEqual(a['stage'],'EXPANSION');s['bars'][-1].update(close=1,high=1.02,low=.94,volume=1000);b=analyze(s,o,NOW);self.assertEqual(b['stage'],'FUEL BUILDING');h=update_history({},[a],NOW);h=update_history(h,[b],NOW+timedelta(minutes=15));self.assertEqual(h['history'][-1]['current'],'FUEL BUILDING')
    def test_alert_dedup(self):
        s,o=fixture();a=analyze(s,o,NOW);h=update_history({},[a],NOW);n=len(h['alerts']);h=update_history(h,[a],NOW+timedelta(minutes=15));self.assertEqual(len(h['alerts']),n)
    def test_no_prior_rank_carryover(self):
        s,o=fixture();a=analyze(s,o,NOW);h=update_history({},[a],NOW);h=update_history(h,[],NOW);self.assertIsNone(h['states']['TEST'])
    def test_fair_targets_no_legacy_scores(self):
        stocks=[{'ticker':'B'},{'ticker':'A'},{'ticker':'C'}];cache={'A':{'attempted_at':NOW.isoformat()},'B':{'attempted_at':(NOW-timedelta(hours=1)).isoformat()}};self.assertEqual([x['ticker'] for x in due_targets(stocks,cache,NOW,2)],['C','B'])
    def test_forward_backtest_blocked(self):
        s,o=fixture();a=analyze(s,o,NOW);archive,result=replay({},[(s,a)],NOW);self.assertIsNone(result['false_positive_rate']);self.assertEqual(result['evaluated_signals'],0);self.assertEqual(len(result['cases']),5);self.assertEqual(archive['observations'][0]['observed_at'],NOW.isoformat())
    def test_snapshot_no_duplicate_same_bar(self):
        s,o=fixture();a=analyze(s,o,NOW);ar,_=replay({},[(s,a)],NOW);ar,_=replay(ar,[(s,a)],NOW+timedelta(minutes=15));self.assertEqual(len(ar['observations']),1)
    def test_failed_refresh_preserves_historical(self):
        s,o=fixture();x=merge_observation(o,{'borrow':{'error':'HTTP403'}});self.assertTrue(x['borrow']['stale']);self.assertEqual(x['borrow']['ctb'],100)
    def test_session_holiday_unknown(self):
        self.assertEqual(session_state({},NOW)['name'],'검증 불가');self.assertEqual(session_state({'status':'ok','date':'2026-10-22','session':None},NOW)['name'],'휴장')
    def test_intraday_future_is_not_confirmation(self):
        s,o=fixture();s['intraday']=[{**b,'time':(NOW+timedelta(hours=1)).isoformat()} for b in s['bars'][-8:]];self.assertFalse(analyze(s,o,NOW)['intraday']['valid'])
if __name__=='__main__':unittest.main()
