import copy,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from hunter.time_machine import known,no_future,run_detection,et_instant
from hunter.time_machine_reconstruct import reconstruct,normalize,envelope,history,SOURCE

NOW=et_instant('2026-10-15T12:00')
def bars():
    return [{'t':(NOW-timedelta(days=40-i)).replace(hour=4,minute=0).isoformat(),'o':2,'h':2.2,'l':1.8,'c':2,'v':1000,'vw':2} for i in range(40)]
class FakeClient:
    def __init__(self):self.requests=[];self.calls=0;self.errors=[]
    async def get(self,url,params):
        self.requests.append((url,dict(params)));self.calls+=1
        if url!=SOURCE:
            return [{'symbol':'UNSEEN','name':'Future Name','exchange':'NASDAQ'}] if params['status']=='active' else [{'symbol':'DELISTED','name':'Changed Name','exchange':'OTC','tradable':False}]
        return {'bars':{s:bars() if params['timeframe']=='1Day' else [] for s in params['symbols'].split(',')},'next_page_token':None}
class ReconstructionTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_unseen_and_inactive_enter_unchanged_engine(self):
        client=FakeClient()
        with patch('hunter.time_machine.analyze',return_value={'coverage':0,'candidate':False}) as engine:
            r=await reconstruct(client,NOW)
        stocks=[x.args[0] for x in engine.call_args_list]
        self.assertEqual({s['ticker'] for s in stocks},{'UNSEEN','DELISTED'})
        self.assertTrue(all('Future Name'!=s['name'] for s in stocks))
        self.assertEqual(r['result']['acquisition_mode'],'HISTORICAL RECONSTRUCTION')
        self.assertEqual(r['result']['status'],'PARTIAL REPLAY')
        self.assertEqual(r['result']['coverage_report']['historical_listing_verified'],0)
        self.assertIsNone(r['result']['coverage_report']['missing_universe_count'])
        self.assertTrue(all(not x.args[1] for x in engine.call_args_list))
        for url,p in client.requests:
            if url==SOURCE:
                self.assertEqual(p['adjustment'],'raw');self.assertEqual(p['asof'],'2026-10-15');self.assertEqual(p['end'],NOW.isoformat())
    async def test_real_engine_no_synthetic_short_pressure(self):
        r=await reconstruct(FakeClient(),NOW)
        self.assertEqual(r['result']['usable_price_stocks'],2)
        self.assertEqual(r['result']['candidate_count'],0)
        self.assertFalse(r['snapshot']['universe_complete'])
    async def test_access_failure_is_not_zero_market_coverage_claim(self):
        c=FakeClient()
        async def fail(url,p):c.errors.append({'status':403});return None
        c.get=fail;r=await reconstruct(c,NOW)
        self.assertEqual(r['result']['status'],'NOT REPRODUCIBLE')
        self.assertIsNone(r['result']['coverage_report']['historical_universe_size'])
    async def test_pagination_every_page(self):
        c=FakeClient();n=0
        async def pages(url,p):
            nonlocal n;n+=1
            return {'bars':{'X':[{'t':str(n)}]},'next_page_token':'next' if n==1 else None}
        c.get=pages;r=await history(c,['X'],NOW,'1Day');self.assertEqual(len(r['X']),2)
    async def test_china_unverified_not_guessed(self):
        r=await reconstruct(FakeClient(),NOW,'china');self.assertEqual(r['result']['examined'],0);self.assertEqual(r['result']['china_unverified'],2)

class HistoricalClocksTests(unittest.TestCase):
    def test_retrieved_today_is_not_automatically_future_information(self):
        r=envelope(1,NOW.isoformat(),NOW.isoformat(),(NOW+timedelta(days=1)).isoformat(),'aggregate completion; vintage unverified')
        self.assertFalse(known(r,NOW));self.assertTrue(known(r,NOW,True))
        r.pop('availability_basis');self.assertFalse(known(r,NOW,True))
    def test_published_available_and_event_future_are_rejected(self):
        r=envelope(1,NOW.isoformat(),NOW.isoformat(),(NOW+timedelta(days=1)).isoformat(),'basis')
        for key in ('event_time','available_at','published_at'):
            v=copy.deepcopy(r);v[key]=(NOW+timedelta(seconds=1)).isoformat();self.assertFalse(known(v,NOW,True))
    def test_nested_future_sec_is_still_rejected_but_retrieval_allowed(self):
        later=(NOW+timedelta(days=1)).isoformat()
        v={'retrieved_at':later,'sec':[{'accepted':later},{'accepted':NOW.isoformat()}]}
        clean=no_future(v,NOW,True);self.assertEqual(clean['retrieved_at'],later);self.assertEqual(len(clean['sec']),1)
    def test_current_session_daily_and_future_intraday_excluded(self):
        raw=[{'t':'2026-10-15T04:00:00Z','o':1,'h':2,'l':1,'c':2,'v':100}]
        self.assertFalse(normalize(raw,NOW,'1Day'))
        raw[0]['t']=(NOW-timedelta(minutes=24)).isoformat();self.assertFalse(normalize(raw,NOW,'5Min'))
        raw[0]['t']=(NOW-timedelta(minutes=25)).isoformat();self.assertEqual(len(normalize(raw,NOW,'5Min')),1)
    def test_no_outcome_archive_or_live_provider_import(self):
        from pathlib import Path
        s=Path('hunter/time_machine_reconstruct.py').read_text()
        for forbidden in ('time_machine_evaluate','squeeze-cache','squeeze-hunter.json','squeeze_telegram','from .providers'):
            self.assertNotIn(forbidden,s)
