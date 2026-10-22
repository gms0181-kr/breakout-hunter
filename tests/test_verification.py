import copy,unittest
from datetime import datetime,timedelta,timezone
from hunter.verification import verify,dilution,market,short_pressure,INSTRUMENTS
from hunter.core import engine_scores,rank
NOW='2026-10-22T20:00:00+00:00'
def stock():
    start=datetime(2026,7,1,tzinfo=timezone.utc)
    bars=[{'time':(start+timedelta(days=i)).isoformat(),'available_at':(start+timedelta(days=i+1)).isoformat(),'open':10,'close':10,'low':9.9,'high':10.1,'volume':100,'vwap':10} for i in range(80)]
    return {'ticker':'TEST','feed':'IEX','bars':bars,'sec':{}}
def docs():return [{'source':'https://www.sec.gov/Archives/test.htm','sha256':'a','known_at':'2026-10-20T12:00:00+00:00'}]
def safe():
    return {'review_known_at':'2026-10-20T12:00:00+00:00','review_valid_until':'2026-10-23T00:00:00+00:00','reviewed':True,'coverage_complete':True,'supply_coverage':dict.fromkeys(INSTRUMENTS,True),'documents':docs(),'supply_facts':[{'security_id':'one','source':docs()[0]['source'],'known_at':'2026-10-20T12:00:00+00:00','effective_at':'2026-10-20T12:00:00+00:00','valid_until':'2026-10-23T00:00:00+00:00','reviewed':True,'evidence':'Reviewed contract restrictions through cutoff','share_basis_verified':True,'new_issuance_now':False,'free_sale_now':False}]}
class VerificationTests(unittest.TestCase):
    def test_missing_never_scores(self):
        v=verify({},NOW);self.assertIsNone(v['score']);self.assertEqual(v['grade'],'검증 불가')
    def test_volume_only_not_capital(self):
        s=stock();s['bars'][-1].update(volume=2000,close=9.9,low=9.8,vwap=10)
        m=market(s,NOW);self.assertFalse(m['confirmed_capital'])
    def test_no_vwap_or_pressure_has_no_assumed_points(self):
        s=stock();[b.pop('vwap') for b in s['bars']];m=market(s,NOW)
        self.assertIsNone(m['checks']['capital']['above_vwap']);self.assertIsNone(m['checks']['capital']['buy_pressure']);self.assertEqual(m['capital_coverage'],22)
    def test_support_route_does_not_need_oversold(self):
        s=stock();s['bars'][-3]['low']=9.95;s['bars'][-2]['low']=9.96;s['bars'][-1].update(low=9.97,close=10.05,volume=300)
        m=market(s,NOW);self.assertTrue(m['confirmed_structure']);self.assertIn('SUPPORT',m['structure_type']);self.assertFalse(m['checks']['oversold']['rsi_oversold'])
    def test_oversold_route_independent(self):
        s=stock()
        for i,b in enumerate(s['bars'][-35:]):
            c=10-i*.18;b.update(open=c+.05,close=c,low=c-.05,high=c+.1,volume=200-i*3,vwap=c+.02)
        for i,b in enumerate(s['bars'][-4:]):b.update(open=3.9,close=3.9,low=3.88,high=4.02,volume=50-i*5,vwap=3.95)
        s['bars'][-1].update(open=3.9,close=4,low=3.89,high=4.01,volume=500,vwap=3.95)
        m=market(s,NOW);self.assertTrue(m['checks']['oversold']['rsi_oversold']);self.assertTrue(m['confirmed_structure'])
    def test_break_of_support(self):
        s=stock();s['bars'][-1].update(low=8,close=8.1,open=8.2,high=8.3)
        m=market(s,NOW);self.assertFalse(m['checks']['support']['support_intact']);self.assertFalse(m['confirmed_structure'])
    def test_future_bars_cannot_change_result(self):
        s=stock();before=market(s,NOW);s['bars'].append({'time':'2027-01-01T00:00:00+00:00','available_at':'2027-01-02T00:00:00+00:00','open':100,'high':200,'low':100,'close':200,'volume':1000000})
        self.assertEqual(before,market(s,NOW))
    def test_undated_bars_not_historical_evidence(self):
        s=stock();[b.pop('available_at') for b in s['bars']];self.assertIsNone(market(s,NOW)['capital'])
    def test_keyword_is_not_safe(self):
        self.assertIsNone(dilution({'documents':docs(),'risk_flags':['CLOSING','EFFECT'],'immediately_sellable':False},NOW)['score'])
    def test_all_supply_evidence_required(self):
        s=safe();self.assertEqual(dilution(s,NOW)['score'],40);s['supply_coverage']['ELOC']=False;self.assertIsNone(dilution(s,NOW)['score'])
    def test_risk_independent_even_if_other_instruments_unknown(self):
        s=safe();s['supply_facts'][0]['free_sale_now']=True;s['coverage_complete']=False;self.assertEqual(dilution(s,NOW)['score'],0)
    def test_split_basis_missing_cannot_prove_gap(self):
        s=safe();s['supply_facts'][0]['share_basis_verified']=False;self.assertIsNone(dilution(s,NOW)['score'])
    def test_future_or_expired_supply_not_safe(self):
        for field,value in [('known_at','2027-01-01T00:00:00+00:00'),('valid_until','2026-10-01T00:00:00+00:00')]:
            s=safe();s['supply_facts'][0][field]=value;self.assertIsNone(dilution(s,NOW)['score'])
    def test_short_zero_single_source_not_squeeze(self):
        s=stock();s['short']={'cross_verified':True,'ctb':1000,'available':0};v=short_pressure(s,NOW);self.assertIsNone(v['score'])
    def test_crossverification_requires_matching_asof_and_values(self):
        s=stock();obs=[{'metric':'ctb','value':100,'source':u,'as_of':'2026-10-22T19:30:00+00:00','known_at':'2026-10-22T19:31:00+00:00'} for u in ['https://chartexchange.com/a','https://fintel.io/b']];s['short']={'observations':obs};self.assertEqual(short_pressure(s,NOW)['score'],1);obs[1]['value']=200;self.assertIsNone(short_pressure(s,NOW)['score'])
    def test_old_engine_scores_preserved(self):
        s=stock();before=engine_scores(s);_,scored=rank([s]);self.assertEqual(scored[0]['scores'],before['scores']);self.assertIn('verification',scored[0])
    def test_b_and_a_require_joint_market_signals(self):
        s=stock();s['sec']=safe();self.assertNotEqual(verify(s,NOW)['grade'],'A')

    def test_real_classification_transitions(self):
        s=stock();s['bars'][-3].update(volume=300,low=9.95);s['bars'][-2].update(low=9.96);s['bars'][-1].update(volume=500,low=9.97,close=10.05)
        s['sec']={'documents':docs()};self.assertEqual(verify(s,NOW)['grade'],'B')
        s['sec']=safe();self.assertEqual(verify(s,NOW)['grade'],'A')
        s['sec']['supply_facts'][0]['new_issuance_now']=True;self.assertEqual(verify(s,NOW)['grade'],'C')
    def test_future_review_does_not_make_past_safe(self):
        s=safe();s['review_known_at']='2027-01-01T00:00:00+00:00';self.assertIsNone(dilution(s,NOW)['score'])
    def test_incomplete_daily_bar_not_used(self):
        s=stock();a=market(s,NOW);s['bars'].append({**s['bars'][-1],'time':'2026-10-22T04:00:00+00:00','complete':False,'close':100,'high':100,'volume':100000});self.assertEqual(a,market(s,NOW))
    def test_future_borrow_not_displayed_in_past(self):
        s=stock();s['enrichment']={'borrow':{'ctb':500,'observed_at':'2027-01-01T00:00:00Z','as_of':'2027-01-01T00:00:00Z'}};self.assertEqual(short_pressure(s,NOW)['source_observation'],{})
