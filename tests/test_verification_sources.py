import unittest
from unittest.mock import patch
from hunter.sec import analyze
from hunter.inlf_case import replay_inlf
from hunter.verification import dilution

class SourcesTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_and_attachment_clauses_do_not_certify_gap(self):
        async def fake(session,url,**kwargs):
            if url.endswith('index.json'):return {'directory':{'item':[{'name':'ex10-1.htm'}]}}
            return '<p>Registered direct offering. Warrants are immediately exercisable at $1.60 per share. The closing is expected. A 9.99% blocker applies. Reverse stock split.</p>'
        with patch.dict('os.environ',{'SEC_USER_AGENT':'test contact'}),patch('hunter.sec.fetch',fake),patch('hunter.sec.asyncio.sleep'):
            sec=await analyze(None,1,{'timeline':[{'source':'https://www.sec.gov/Archives/a.htm','filed':'2026-10-20','accepted':'2026-10-20T12:00:00Z','form':'6-K'}]})
        self.assertEqual(len(sec['documents']),2)
        self.assertTrue({'RD','EXERCISE_NOW','REVERSE_SPLIT'}<=set(sec['risk_flags']))
        self.assertTrue(any(e['numbers'] for e in sec['clause_evidence']))
        self.assertFalse(sec['reviewed']);self.assertIsNone(dilution(sec,'2099-01-01T00:00:00Z')['score'])
    async def test_inlf_without_credentials_never_invents_detection(self):
        with patch.dict('os.environ',{},clear=True):r=await replay_inlf(None)
        self.assertIsNone(r['detected_before_spike']);self.assertEqual(r['sessions'],[])
    async def test_inlf_cutoff_excludes_later_minutes_and_filings(self):
        async def fake(session,url,**kwargs):
            if kwargs['params']['timeframe']=='1Day':return {'bars':[{'t':'2026-10-20T04:00:00Z','o':1,'h':2,'l':1,'c':2,'v':100,'vw':1.5}]}
            return {'bars':[{'t':'2026-10-20T19:54:00Z','o':1,'h':2,'l':1,'c':1.5,'v':100,'vw':1.4},{'t':'2026-10-20T19:55:00Z','o':2,'h':100,'l':2,'c':100,'v':99999,'vw':90}]}
        async def timeline(*args):return {'timeline':[{'accepted':'2026-10-20T19:54:00Z'},{'accepted':'2026-10-20T19:56:00Z'}]}
        with patch.dict('os.environ',{'ALPACA_API_KEY':'test','ALPACA_API_SECRET':'test'}),patch('hunter.inlf_case.fetch',fake),patch('hunter.inlf_case.sec_timeline',timeline):r=await replay_inlf(None,1)
        row=r['sessions'][0];self.assertEqual(row['minute_count'],1);self.assertEqual(row['observed_price'],1.5);self.assertEqual(len(row['filings_available_by_cutoff']),1);self.assertIsNone(row['detected']);self.assertIsNone(row['ctb_change'])

    async def test_inlf_null_bars_is_explicit_unavailable(self):
        async def fake(*args,**kwargs):return {'bars':None}
        with patch.dict('os.environ',{'ALPACA_API_KEY':'test','ALPACA_API_SECRET':'test'}),patch('hunter.inlf_case.fetch',fake):r=await replay_inlf(None)
        self.assertEqual(r['price_response_status'],'no_bars');self.assertNotIn('error',r)
