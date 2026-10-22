"""Telegram transport. Only explicit chat ID from Secrets; no recipient discovery."""
import json,os,re
from datetime import timezone
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
from .squeeze_signals import instant,finite

STAGE_LABELS={'DORMANT':'1단계 공매도 압박 잠복','FUEL_BUILDING':'2단계 숏 압박 축적','SETUP':'3단계 상승 준비','IGNITION':'4단계 상승 점화','EXPANSION':'5단계 상승 가속'}
KINDS={'ctb_surge':'CTB 급등','borrow_drop':'대차 잔량 급감','pressure_jump':'숏 압박 점수 상승','stage_change':'진행 단계 변경','breakout_inflow':'저항 돌파·거래대금 증가','market_early_watch':'가격·거래대금 선행 관찰','new_supply_disclosure':'신규 희석 관련 공시','historical_supply_discovery':'과거 공시 신규 수집','connection_test':'텔레그램 연결 테스트'}

def stamp(value):
    d=instant(value)
    if not d:return '시각 미확인'
    return d.astimezone(ZoneInfo('Asia/Seoul')).strftime('%m-%d %H:%M KST')+' / '+d.astimezone(ZoneInfo('America/New_York')).strftime('%m-%d %H:%M ET')

def display(value):
    if value is None:return '미확인'
    if isinstance(value,str):return STAGE_LABELS.get(value.replace(' ','_'),value)
    if finite(value):return format(value,',.4f').rstrip('0').rstrip('.')
    return json.dumps(value,ensure_ascii=False)

def alert_text(a):
    kind=a.get('kind');title=a['ticker']+(' — '+a['company_name'] if a.get('company_name') else '')
    lines=[title+' | '+KINDS.get(kind,kind or '경보'),'발생 '+stamp(a.get('occurred_at')),'근거 '+stamp(a.get('source_at'))]
    current=a.get('current')
    if kind=='market_early_watch' and isinstance(current,dict):
        lines.append('당일 변화 '+display(current.get('change_pct'))+'(%) · 거래대금 비교 '+display(current.get('dollar_ratio'))+'(배)')
    else:
        unit='(%)' if kind=='ctb_surge' else '(주)' if kind=='borrow_drop' else '(점)' if kind=='pressure_jump' else ''
        lines.append(display(a.get('previous'))+unit+' → '+display(current)+unit)
    lines.append(str(a.get('evidence') or '')[:400])
    lines.append('https://gms0181-kr.github.io/breakout-hunter/#short-squeeze/'+a['ticker'])
    return '\n'.join(lines[:-1])[:850]+'\n'+lines[-1]

def deliver_telegram(alerts,previous,now,send=None):
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip();chat=os.getenv('TELEGRAM_CHAT_ID','').strip()
    sent=list(previous.get('accepted_ids',[]));out={'status':'not_configured','note':'GitHub Secrets TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 설정 필요','checked_at':now.isoformat(),'accepted_ids':sent,'accepted_this_run':0,'failed_this_run':0}
    if not token and not chat:return out
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token) or not re.fullmatch(r'-?[1-9]\d*',chat):
        out.update(status='invalid_configuration',note='텔레그램 Secret 누락 또는 형식 오류');return out
    out.update(status='configured',note='설정됨 · 이번 실행의 신규 경보 API 접수 대기')
    retry=instant(previous.get('retry_not_before'))
    if retry and retry>now:
        out.update(status='rate_limited',retry_not_before=retry.isoformat(),note='Telegram 요청 제한 후 재시도 대기');return out
    pending=[a for a in alerts if a['id'] not in set(sent) and instant(a.get('occurred_at')) and 0<=(now-instant(a['occurred_at'])).total_seconds()<=3600]
    pending.sort(key=lambda a:a['occurred_at'])
    text='BREAKOUT HUNTER 1.0\nIEX 지연 자료 · 숏스퀴즈 확정·매수 신호 아님\n';batch=[]
    for a in pending[:20]:
        block='\n'+alert_text(a)+'\n'
        if len(text)+len(block)>3600:break
        text+=block;batch.append(a)
    if not batch:return out
    try:
        request=Request('https://api.telegram.org/bot'+token+'/sendMessage',data=json.dumps({'chat_id':chat,'text':text,'link_preview_options':{'is_disabled':True}},ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
        response=(send or urlopen)(request,timeout=15)
        with response:
            body=json.loads(response.read())
            if not 200<=response.status<300 or body.get('ok') is not True:raise RuntimeError('telegram_rejected')
            result=body.get('result',{})
            if str(result.get('chat',{}).get('id'))!=chat or not isinstance(result.get('message_id'),int):raise RuntimeError('recipient_not_verified')
        out.update(status='telegram_api_accepted',note='Telegram API가 지정 대화로 메시지 접수 확인 · 실제 열람 여부 미확인',accepted_this_run=len(batch),last_accepted_at=now.isoformat(),accepted_ids=(sent+[a['id'] for a in batch])[-2000:])
    except Exception as exc:
        # Exceptions may embed the bot token URL. Persist neither URL nor raw errors.
        out.update(status='delivery_failed',note='텔레그램 접수 실패 · 다음 스캔 재시도',failed_this_run=len(batch))
        if getattr(exc,'code',None)==429:
            from datetime import timedelta
            out.update(status='rate_limited',note='Telegram 요청 제한 · 재시도 대기',retry_not_before=(now+timedelta(minutes=15)).isoformat())
    return out
