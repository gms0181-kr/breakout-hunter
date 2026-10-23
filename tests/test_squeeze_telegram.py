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
    def setUp(self):
        p=patch('time.sleep');p.start();self.addCleanup(p.stop)
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
        self.assertLessEqual(len(sent[0]),3600);self.assertLess(r['accepted_this_run'],20);self.assertEqual(len(r['accepted_ids']),r['accepted_this_run']);self.assertIn('탐지 근거',sent[0])
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

class TelegramActivationTests(unittest.TestCase):
    def test_activation_skips_309_old_alerts_and_delivers_only_new(self):
        old=[{**alert(i),'occurred_at':(NOW-timedelta(minutes=5)).isoformat()} for i in range(309)]
        previous={'activation_after':(NOW-timedelta(minutes=1)).isoformat()}
        calls=[]
        def send(req,timeout):calls.append(req);return Response()
        with patch.dict(os.environ,ENV,clear=True):
            result=deliver_telegram(old+[alert(400)],previous,NOW,send)
            repeated=deliver_telegram(old+[alert(400)],result,NOW,send)
        self.assertEqual(result['accepted_ids'],[alert(400)['id']])
        self.assertEqual(len(calls),1)
        self.assertEqual(repeated['accepted_this_run'],0)
        self.assertEqual(result['activation_after'],previous['activation_after'])
        self.assertEqual(result['last_message_id'],7)
    def test_safe_diagnostics_distinguish_partial_and_format_errors(self):
        from hunter.squeeze_telegram import configuration_diagnostics
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'invalid','TELEGRAM_CHAT_ID':'42'},clear=True):
            d=configuration_diagnostics()
        self.assertEqual(d,{'token_present':True,'chat_id_present':True,'token_format_valid':False,'chat_id_format_valid':True})
        self.assertNotIn('invalid',json.dumps(d))
    def test_delivery_failure_keeps_activation_boundary_for_retry(self):
        previous={'activation_after':(NOW-timedelta(minutes=1)).isoformat()}
        with patch.dict(os.environ,ENV,clear=True):
            failed=deliver_telegram([alert()],previous,NOW,lambda *a,**k:Response({'ok':False}))
            result=deliver_telegram([alert()],failed,NOW,lambda *a,**k:Response())
        self.assertEqual(result['accepted_this_run'],1)

class PremiumTelegramTests(unittest.TestCase):
    def setUp(self):
        p=patch('time.sleep');p.start();self.addCleanup(p.stop)
    def send_alerts(self,alerts,previous=None,fail_at=None):
        calls=[]
        def send(req,timeout):
            calls.append(json.loads(req.data))
            return Response({'ok':False}) if len(calls)==fail_at else Response({'ok':True,'result':{'message_id':len(calls)+20,'chat':{'id':42}}})
        with patch.dict(os.environ,ENV,clear=True):result=deliver_telegram(alerts,previous or {},NOW,send)
        return result,calls
    def test_price_first_html_and_brcb_example_not_hardcoded(self):
        a={**alert(),'ticker':'BRCB','kind':'market_early_watch','current':{'change_pct':11.09,'dollar_ratio':2.29}}
        r,c=self.send_alerts([a]);self.assertIn('+11.09(%)',c[0]['text']);self.assertIn('2.29(배)',c[0]['text']);self.assertIn('🟡',c[0]['text']);self.assertEqual(c[0]['parse_mode'],'HTML')
        self.assertEqual(r['format_version'],'premium-html-v1')
    def test_ctb_borrow_zero_and_missing(self):
        for kind,value,unit in [('ctb_surge',50,'(%)'),('borrow_drop',0,'(주)'),('pressure_jump',None,'(점)')]:
            text=alert_text({**alert(),'kind':kind,'current':value})
            self.assertIn(('미확인' if value is None else str(value))+unit,text)
    def test_verified_stage_and_risk_priority(self):
        from hunter.squeeze_telegram import signal_style
        for stage,emoji in [('SETUP','🟠'),('IGNITION','🚨'),('EXPANSION','🔴')]:
            self.assertEqual(signal_style({**alert(),'current':stage})[0],emoji)
        self.assertEqual(signal_style({**alert(),'kind':'new_supply_disclosure'})[0],'⚠️')
    def test_html_special_characters_and_long_company(self):
        from html.parser import HTMLParser
        text=alert_text({**alert(),'company_name':'A&B <script> "x"'*100,'evidence':'<bad>&'*100})
        self.assertNotIn('<script>',text);self.assertIn('&amp;',text);self.assertLess(len(text),1800)
        class Parser(HTMLParser):
            def handle_starttag(self,tag,attrs):self.assert_tag(tag)
            def assert_tag(self,tag):assert tag=='b'
        Parser().feed(text)
    def test_split_max_three_tickers_and_individual_ignition(self):
        alerts=[{**alert(i),'ticker':'T'+str(i),'kind':'ctb_surge','current':50} for i in range(10)]
        r,c=self.send_alerts(alerts)
        self.assertEqual(r['accepted_this_run'],10);self.assertEqual(len(c),4)
        self.assertTrue(all(len(p['reply_markup']['inline_keyboard'])<=3 and len(p['text'])<=3600 for p in c))
        r,c=self.send_alerts([{**alert(i),'ticker':'T'+str(i)} for i in range(3)])
        self.assertEqual(len(c),3)
    def test_partial_failure_receipts_and_retry_no_duplicates(self):
        alerts=[{**alert(i),'ticker':'T'+str(i)} for i in range(3)]
        r,c=self.send_alerts(alerts,fail_at=2)
        self.assertEqual(r['accepted_this_run'],1);self.assertEqual(len(r['message_receipts']),1)
        again,c2=self.send_alerts(alerts,r)
        self.assertEqual(again['accepted_this_run'],2);self.assertNotIn('T0',c2[0]['text']);self.assertEqual(len(again['message_receipts']),3)
        final,c3=self.send_alerts(alerts,again);self.assertEqual(c3,[])
    def test_timestamps_source_is_distinct_and_dst(self):
        from hunter.squeeze_telegram import stamp
        self.assertIn('10-23 09:00 KST / 10-22 20:00 ET',stamp(NOW.isoformat()))
        self.assertIn('01-22 19:00 ET',stamp('2026-01-23T00:00:00+00:00'))
        text=alert_text({**alert(),'source_at':(NOW-timedelta(days=2)).isoformat()})
        self.assertIn('발생:',text);self.assertIn('데이터 근거:',text);self.assertIn('10-21',text)
    def test_buttons_ticker_routes_and_no_unsafe_url(self):
        from hunter.squeeze_telegram import detail_url
        r,c=self.send_alerts([{**alert(),'ticker':'A/B&X'}])
        button=c[0]['reply_markup']['inline_keyboard'][0][0]
        self.assertEqual(button['text'],'🔗 종목 상세 분석')
        self.assertEqual(button['url'],detail_url('A/B&X'));self.assertTrue(button['url'].endswith('A%2FB%26X'))
    def test_no_new_backlog_replay_and_receipts_survive_upgrade(self):
        previous={'accepted_ids':[alert()['id']],'activation_after':(NOW-timedelta(minutes=1)).isoformat()}
        r,c=self.send_alerts([alert()],previous);self.assertEqual(c,[]);self.assertEqual(r['accepted_ids'],previous['accepted_ids'])

    def test_receipts_survive_rate_limit_and_configuration_failure(self):
        receipt={'message_id':20,'alert_ids':['old']}
        previous={'message_receipts':[receipt],'accepted_ids':['old'],'retry_not_before':(NOW+timedelta(minutes=10)).isoformat()}
        r,c=self.send_alerts([alert()],previous)
        self.assertEqual(r['status'],'rate_limited');self.assertEqual(r['message_receipts'],[receipt])
        with patch.dict(os.environ,{},clear=True):r=deliver_telegram([],previous,NOW)
        self.assertEqual(r['message_receipts'],[receipt])
