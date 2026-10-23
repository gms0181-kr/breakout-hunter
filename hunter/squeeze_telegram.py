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

HEADER='🚨 <b>BREAKOUT HUNTER 1.0</b>\n📡 <b>PREMIUM SQUEEZE ALERT</b>\n'
SEPARATOR='━━━━━━━━━━━━━━━━━━'

def safe(value,limit=240):
    from html import escape
    return escape(str(value)[:limit],quote=True)

def detail_url(ticker):
    from urllib.parse import quote
    return 'https://gms0181-kr.github.io/breakout-hunter/#short-squeeze/'+quote(str(ticker),safe='')

def signal_style(a):
    kind=a.get('kind');stage=str(a.get('current','')).replace(' ','_') if kind=='stage_change' else ''
    if kind=='new_supply_disclosure':return '⚠️','희석 관련 공시 · 즉시 출회 여부 추가 확인',0
    if stage=='EXPANSION':return '🔴','상승 가속 · 추격 위험 확인',1
    if stage=='IGNITION':return '🚨','상승 점화 · 확정 매수 신호 아님',1
    if stage=='SETUP':return '🟠','상승 준비 · 추가 확인 필요',2
    if kind in ('ctb_surge','borrow_drop','pressure_jump') or stage=='FUEL_BUILDING':return '🟢','초기 포착 · 단일 신호로 숏스퀴즈 확정 불가',3
    return '🟡','탐색 단계 · 숏스퀴즈 확정 아님 · 매수 신호 아님',4

def alert_text(a):
    kind=a.get('kind');emoji,risk,_=signal_style(a);current=a.get('current')
    lines=[emoji+' <b>'+safe(a['ticker'],24)+'</b> '+safe(a.get('company_name',''),100),
           '🔎 <b>'+safe(KINDS.get(kind,kind or '경보'),60)+'</b>']
    if kind=='market_early_watch' and isinstance(current,dict):
        change=current.get('change_pct');ratio=current.get('dollar_ratio')
        if finite(change):lines.append('📈 <b>당일 등락률: '+format(change,'+.2f')+'(%)</b>')
        if finite(ratio):lines.append('🔥 <b>거래대금 비교: '+display(ratio)+'(배)</b>')
    elif kind in ('ctb_surge','borrow_drop','pressure_jump','stage_change'):
        label,unit={'ctb_surge':('💸 CTB','(%)'),'borrow_drop':('📉 대차 가능 주식수','(주)'),
                    'pressure_jump':('🎯 숏 압박 점수','(점)'),'stage_change':('⚡ 단계','')}[kind]
        lines.append(label+': <b>'+safe(display(a.get('previous'))+unit+' → '+display(current)+unit,180)+'</b>')
    elif kind=='connection_test':lines.append('🧪 <b>디자인 연결 테스트 · 실제 종목 경보 아님</b>')
    lines.extend(['📊 <b>탐지 근거</b>\n'+safe(a.get('evidence') or '미확인',180),
                  '🕒 발생: '+safe(stamp(a.get('occurred_at'))),
                  '🔎 데이터 근거: '+safe(stamp(a.get('source_at'))),
                  '⚠️ '+risk])
    return '\n'.join(lines)

def message_batches(pending):
    """Priority is presentation only; never modifies engine scores or states."""
    groups={}
    for a in sorted(pending,key=lambda a:(signal_style(a)[2],a['occurred_at']))[:20]:
        groups.setdefault(a['ticker'],[]).append(a)
    batches=[];batch=[];text=HEADER;buttons=[]
    def flush():
        nonlocal batch,text,buttons
        if batch:batches.append((batch,text,buttons))
        batch=[];text=HEADER;buttons=[]
    for ticker,events in groups.items():
        # One card per ticker, up to five events. Overflow stays pending.
        events=events[:5]
        block='\n'+SEPARATOR+'\n'+'\n\n'.join(alert_text(a) for a in events)+'\n'
        strong=any(a.get('kind')=='stage_change' and a.get('current') in ('IGNITION','EXPANSION') for a in events)
        if batch and (len(buttons)>=3 or len(text)+len(block)>3600 or strong):flush()
        if len(HEADER+block)>3600:
            events=events[:1];block='\n'+SEPARATOR+'\n'+alert_text(events[0])+'\n'
        text+=block;batch.extend(events)
        buttons.append([{'text':'🔗 종목 상세 분석','url':detail_url(ticker)}])
        if strong:flush()
    flush()
    return batches[:6]

def configuration_diagnostics():
    """Only booleans and reason codes; never values, lengths, hashes or URLs."""
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    chat=os.getenv('TELEGRAM_CHAT_ID','').strip()
    return {'token_present':bool(token),'chat_id_present':bool(chat),
            'token_format_valid':bool(re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token)),
            'chat_id_format_valid':bool(re.fullmatch(r'-?[1-9]\d*',chat))}

def deliver_telegram(alerts,previous,now,send=None):
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip();chat=os.getenv('TELEGRAM_CHAT_ID','').strip()
    diagnostics=configuration_diagnostics()
    sent=list(previous.get('accepted_ids',[]));out={'status':'not_configured','note':'GitHub Secrets TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 설정 필요','checked_at':now.isoformat(),'accepted_ids':sent,'accepted_this_run':0,'failed_this_run':0}
    out['configuration']=diagnostics
    for key in ('activation_after','last_accepted_at','last_message_id'):
        if key in previous:out[key]=previous[key]
    if not token and not chat:return out
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token) or not re.fullmatch(r'-?[1-9]\d*',chat):
        out.update(status='invalid_configuration',note='텔레그램 Secret 누락 또는 형식 오류');return out
    out.update(status='configured',note='설정됨 · 이번 실행의 신규 경보 API 접수 대기')
    retry=instant(previous.get('retry_not_before'))
    if retry and retry>now:
        out.update(status='rate_limited',retry_not_before=retry.isoformat(),note='Telegram 요청 제한 후 재시도 대기');return out
    activation=instant(previous.get('activation_after'))
    pending=[a for a in alerts if (not activation or (instant(a.get('occurred_at')) and instant(a['occurred_at'])>activation)) if a['id'] not in set(sent) and instant(a.get('occurred_at')) and 0<=(now-instant(a['occurred_at'])).total_seconds()<=3600]
    out['format_version']='premium-html-v1'
    out['message_receipts']=list(previous.get('message_receipts',[]))[-100:]
    batches=message_batches(pending)
    for index,(batch,text,buttons) in enumerate(batches):
        if index:
            # Same-chat messages are deliberately paced, including private chats.
            import time
            time.sleep(3.1)
        try:
            payload={'chat_id':chat,'text':text,'parse_mode':'HTML','link_preview_options':{'is_disabled':True},'reply_markup':{'inline_keyboard':buttons}}
            request=Request('https://api.telegram.org/bot'+token+'/sendMessage',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
            response=(send or urlopen)(request,timeout=15)
            with response:
                body=json.loads(response.read())
                if not 200<=response.status<300 or body.get('ok') is not True:raise RuntimeError('telegram_rejected')
                result=body.get('result',{})
                if str(result.get('chat',{}).get('id'))!=chat or not isinstance(result.get('message_id'),int):raise RuntimeError('recipient_not_verified')
            ids=[a['id'] for a in batch];sent.extend(ids)
            out['message_receipts'].append({'message_id':result['message_id'],'accepted_at':now.isoformat(),'alert_ids':ids,'format_version':'premium-html-v1'})
            out['message_receipts']=out['message_receipts'][-100:]
            out.update(status='telegram_api_accepted',note='Telegram API가 지정 대화로 메시지 접수 확인 · 실제 열람 여부 미확인',accepted_this_run=out['accepted_this_run']+len(batch),last_accepted_at=now.isoformat(),last_message_id=result['message_id'],accepted_ids=sent[-2000:])
        except Exception as exc:
            # Never persist raw API errors, destination IDs or token-bearing URLs.
            out.update(status='delivery_failed',note='일부 또는 전체 메시지 접수 실패 · 성공 메시지는 재발송하지 않고 다음 스캔 재시도',failed_this_run=len(batch))
            if getattr(exc,'code',None)==429:
                from datetime import timedelta
                out.update(status='rate_limited',note='Telegram 요청 제한 · 재시도 대기',retry_not_before=(now+timedelta(minutes=15)).isoformat())
            break

    return out

if __name__=='__main__':
    print(json.dumps({'telegram_configuration':configuration_diagnostics()},ensure_ascii=False))
