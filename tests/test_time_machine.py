import copy,json,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from hunter.time_machine import known,et_instant,no_future,run_detection,frozen,digest
from hunter.time_machine_evaluate import evaluate

NOW=datetime(2026,10,22,20,tzinfo=timezone.utc)
def record(value):return {'value':value,'event_time':NOW.isoformat(),'available_at':NOW.isoformat(),'retrieved_at':NOW.isoformat(),'source':'https://example.org/archive'}
def snapshot():return {**record(None),'source_commit':'a'*40,'rows':[{'inputs':{'stock':record({'ticker':'X','name':'X Corp'}),'observation':record({})}}]}
class TimeMachineTests(unittest.TestCase):
    def test_requires_all_four_provenance_fields(self):
        r=record(1);self.assertTrue(known(r,NOW))
        for key in ('event_time','available_at','retrieved_at','source'):
            broken=copy.deepcopy(r);broken.pop(key);self.assertFalse(known(broken,NOW))
    def test_future_forbidden_in_each_clock(self):
        for key in ('event_time','available_at','retrieved_at'):
            r=record(1);r[key]=(NOW+timedelta(seconds=1)).isoformat();self.assertFalse(known(r,NOW))
    def test_before_first_archive_not_reproducible(self):
        r=run_detection(snapshot(),(NOW-timedelta(seconds=1)).isoformat());self.assertEqual(r['status'],'NOT REPRODUCIBLE');self.assertFalse(r['top20'])
    def test_et_dst_correct_and_ambiguous_rejected(self):
        self.assertEqual(et_instant('2026-10-15T09:30').isoformat(),'2026-10-15T13:30:00+00:00')
        self.assertEqual(et_instant('2026-01-15T09:30').hour,14)
        for s in ('2026-11-01T01:30','2026-03-08T02:30'):
            with self.assertRaises(ValueError):et_instant(s)
    def test_nested_future_sec_borrow_and_bars_removed(self):
        v={'sec':{'timeline':[{'accepted':(NOW+timedelta(days=1)).isoformat()},{'accepted':NOW.isoformat()}]},'borrow':{'as_of':(NOW+timedelta(seconds=1)).isoformat()},'bars':[{'time':(NOW+timedelta(days=1)).isoformat()}]}
        clean=no_future(v,NOW);self.assertNotIn('borrow',clean);self.assertEqual(len(clean['sec']['timeline']),1);self.assertEqual(clean['bars'],[])
    def test_future_observation_does_not_reach_engine(self):
        s=snapshot();s['rows'][0]['inputs']['observation']['available_at']=(NOW+timedelta(seconds=1)).isoformat()
        with patch('hunter.time_machine.analyze',return_value={'coverage':0,'candidate':False}) as analyze:
            r=run_detection(s,NOW.isoformat());self.assertEqual(analyze.call_args.args[1],{});self.assertEqual(r['rejected_inputs'],1)
    def test_partial_never_enters_verified_success_rate(self):
        result=run_detection(snapshot(),NOW.isoformat());self.assertEqual(result['status'],'PARTIAL REPLAY');e=evaluate(result['frozen'],{});self.assertIsNone(e['verified_success_rate'])
    def test_china_unknown_not_inferred_from_name(self):
        s=snapshot();s['rows'][0]['inputs']['stock']['value']['name']='China Holdings'
        r=run_detection(s,NOW.isoformat(),'china');self.assertEqual(r['examined'],0);self.assertEqual(r['china_unverified'],1)
    def test_hash_prevents_post_outcome_candidate_change(self):
        lock=frozen([],NOW.isoformat(),'all','a');lock['candidates'].append({'ticker':'WINNER'})
        with self.assertRaises(ValueError):evaluate(lock,{})
    def test_no_future_reader_or_telegram_import_in_detection(self):
        source=Path('hunter/time_machine.py').read_text();self.assertNotIn('time_machine_evaluate',source);self.assertNotIn('squeeze_telegram',source)
    def test_new_historical_listing_does_not_use_current_universe(self):
        s=snapshot();s['rows'][0]['inputs']['stock']['value']['ticker']='DELISTED'
        with patch('hunter.time_machine.analyze',return_value={'coverage':0,'candidate':False}) as a:
            run_detection(s,NOW.isoformat());self.assertEqual(a.call_args.args[0]['ticker'],'DELISTED')
    def test_ohlc_target_and_stop_same_bar_is_ambiguous(self):
        lock=frozen([{'ticker':'X','name':'X','status':'VERIFIED REPLAY'}],NOW.isoformat(),'all','a')
        bars=[{'event_time':'2026-10-23T20:00:00+00:00','session_open':'2026-10-23T13:30:00+00:00','open':10,'high':12,'low':8,'close':11,'volume':10000}]
        r=evaluate(lock,{'X':{'bars':bars,'price_basis_verified':True}},slippage_bps=0)
        self.assertEqual(r['rows'][0]['horizons']['1']['target_stop_order'],'ambiguous_same_daily_bar');self.assertEqual(r['verified_count'],0)
    def test_split_and_price_basis_uncertainty_prevents_false_return(self):
        lock=frozen([{'ticker':'X','name':'X','status':'PARTIAL REPLAY'}],NOW.isoformat(),'all','a')
        b={'event_time':'2026-10-23T20:00:00+00:00','session_open':'2026-10-23T13:30:00+00:00','open':10,'high':12,'low':8,'close':11,'volume':10000}
        for extra in ({'price_basis_verified':False},{'price_basis_verified':True,'split_events':[{'ex_date':'2026-10-23'}]}):
            r=evaluate(lock,{'X':{'bars':[b],**extra}});self.assertEqual(r['rows'][0]['status'],'NOT EVALUABLE')
    def test_actual_engine_reused_without_weight_replacement(self):
        from hunter.squeeze_signals import WEIGHTS
        self.assertEqual(WEIGHTS,{'short_pressure':30,'capital_inflow':25,'price_structure':20,'dilution_gap':20,'catalyst':5})
