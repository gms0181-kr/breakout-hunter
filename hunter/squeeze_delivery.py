"""Optional authenticated destination URL from GitHub Secrets; durable dedup receipt."""
import json,os
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from .squeeze_signals import instant

def deliver(alerts,previous,now,send=None):
    destination=os.getenv('SQUEEZE_ALERT_WEBHOOK_URL','')
    sent=list(previous.get('accepted_ids',[]));out={'checked_at':now.isoformat(),'accepted_ids':sent,'accepted_this_run':0,'failed_this_run':0,'status':'not_configured','note':'외부 알림 목적지 미연결; 브라우저 종료 시 전달 검증 안 됨'}
    if not destination:return out
    parsed=urlparse(destination)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        out.update(status='invalid_configuration',note='HTTPS 웹훅 주소 검증 실패');return out
    out.update(status='configured',note='HTTP 수신 확인과 실제 사용자 수신은 구분; 수신기 알림 설정 필요')
    pending=[a for a in alerts if a['id'] not in set(sent) and instant(a.get('occurred_at')) and 0<=(now-instant(a['occurred_at'])).total_seconds()<=3600][-20:]
    for alert in pending:
        try:
            payload={'engine':'BREAKOUT HUNTER 1.0','id':alert['id'],'alert':alert,'url':'https://gms0181-kr.github.io/breakout-hunter/#short-squeeze/'+alert['ticker']}
            request=Request(destination,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Idempotency-Key':alert['id']},method='POST')
            response=(send or urlopen)(request,timeout=10)
            with response:
                if not 200<=response.status<300:raise RuntimeError('http_rejected')
            sent.append(alert['id']);out['accepted_this_run']+=1
        except Exception:
            # Never log URL, bearer query strings, response bodies, or exception content.
            out['failed_this_run']+=1
    out['accepted_ids']=sent[-2000:]
    if out['failed_this_run']:out['status']='delivery_failed'
    return out
