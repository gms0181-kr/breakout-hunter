import json,os,re,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path
from hunter.squeeze_telegram import deliver_telegram,alert_text,STAGE_LABELS
from hunter.squeeze_delivery import deliver

NOW=datetime(2026,10,23,0,tzinfo=timezone.utc)
ENV={'TELEGRAM_BOT_TOKEN':'123456:ABCDEFGHIJKLMNOPQRSTUVWX','TELEGRAM_CHAT_ID':'42'}
def alert(i=0):return {'id':'X|watch|'+str(i),'ticker':'X','company_name':'Example Inc.','kind':'stage_change','previous':'SETUP','current':'IGNITION','source_at':NOW.isoformat(),'occurred_at':NOW.isoformat(),'evidence':'관측 근거'}
class Response:
    status=200
    def __init__(self,body=None):self.body=body if body is not None else {'ok':True,'result':{'message_id':7,'chat':{'id':42}}}
    def read(self):return json.dumps(self.body).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass

class TelegramTests(unittest.TestCase):
    def test_missing_and_partial_credentials_never_send(self):
        for env,status in [({},'not_configured'),({'TELEGRAM_CHAT_ID':'42'},'invalid_configuration')]:
            with patch.dict(os.environ,env,clear=True):self.assertEqual(deliver_telegram([alert()],{},NOW,lambda *a,**k:self.fail('sent'))['status'],status)
    def test_actual_request_korean_format_and_dedup(self):
        calls=[]
        def send(request,timeout):calls.append(json.loads(request.data));return Response()
        with patch.dict(os.environ,ENV,clear=True):
            a=deliver_telegram([alert()],{},NOW,send);b=deliver_telegram([alert()],a,NOW,send)
        self.assertEqual(a['status'],'telegram_api_accepted');self.assertEqual(len(calls),1);self.assertEqual(calls[0]['chat_id'],'42');self.assertIn('3단계 상승 준비 → 4단계 상승 점화',calls[0]['text']);self.assertIn('KST',calls[0]['text']);self.assertIn('ET',calls[0]['text']);self.assertEqual(b['accepted_this_run'],0)
    def test_http200_api_rejection_not_acknowledged(self):
        with patch.dict(os.environ,ENV,clear=True):r=deliver_telegram([alert()],{},NOW,lambda *a,**k:Response({'ok':False,'description':'private'}))
        self.assertEqual(r['status'],'delivery_failed');self.assertEqual(r['accepted_ids'],[]);self.assertNotIn('private',str(r))
    def test_recipient_echo_and_message_id_required(self):
        for result in ({'message_id':7,'chat':{'id':99}},{'chat':{'id':42}}):
            with patch.dict(os.environ,ENV,clear=True):r=deliver_telegram([alert()],{},NOW,lambda *a,**k:Response({'ok':True,'result':result}))
            self.assertEqual(r['accepted_ids'],[]);self.assertEqual(r['status'],'delivery_failed')
    def test_channel_receipts_are_independent(self):
        with patch.dict(os.environ,ENV,clear=True):r=deliver([alert()],{'accepted_ids':[alert()['id']]},NOW,lambda *a,**k:Response())
        self.assertEqual(r['telegram']['accepted_this_run'],1);self.assertEqual(r['accepted_this_run'],1)
    def test_batch_length_never_acknowledges_unshown_alerts(self):
        alerts=[{**alert(i),'evidence':'긴근거'*300} for i in range(20)];sent=[]
        def send(req,timeout):sent.append(json.loads(req.data)['text']);return Response()
        with patch.dict(os.environ,ENV,clear=True):r=deliver_telegram(alerts,{},NOW,send)
        self.assertLessEqual(len(sent[0]),3600);self.assertLess(r['accepted_this_run'],20);self.assertEqual(len(r['accepted_ids']),r['accepted_this_run']);self.assertTrue(sent[0].strip().endswith('/X'))
    def test_error_and_token_never_persist(self):
        def fail(*a,**k):raise RuntimeError(ENV['TELEGRAM_BOT_TOKEN'])
        with patch.dict(os.environ,ENV,clear=True):r=deliver_telegram([alert()],{},NOW,fail)
        self.assertNotIn(ENV['TELEGRAM_BOT_TOKEN'],json.dumps(r));self.assertNotIn('api.telegram.org',json.dumps(r));self.assertEqual(r['accepted_ids'],[])
    def test_rate_limit_defers_next_attempt(self):
        def fail(*a,**k):raise HTTPError('https://api.telegram.org/private',429,'rate',None,None)
        with patch.dict(os.environ,ENV,clear=True):
            r=deliver_telegram([alert()],{},NOW,fail);r2=deliver_telegram([alert()],r,NOW+timedelta(minutes=5),lambda *a,**k:self.fail('rate limit ignored'))
        self.assertEqual(r2['status'],'rate_limited');self.assertEqual(r2['accepted_ids'],[])
    def test_stale_and_future_alerts_are_not_sent(self):
        alerts=[{**alert(i),'occurred_at':(NOW+delta).isoformat()} for i,delta in enumerate([timedelta(days=-1),timedelta(minutes=1)])]
        with patch.dict(os.environ,ENV,clear=True):r=deliver_telegram(alerts,{},NOW,lambda *a,**k:self.fail('out of time sent'))
        self.assertEqual(r['accepted_this_run'],0)
    def test_stage_names_match_shared_frontend_labels(self):
        text=Path('public/squeeze-labels.js').read_text();labels={i:n+'단계 '+label for i,n,label in re.findall(r"id:'([^']+)',number:(\d),label:'([^']+)'",text)}
        self.assertEqual(STAGE_LABELS,labels)
