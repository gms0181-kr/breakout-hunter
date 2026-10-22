"""Provider-reported reverse splits, paginated and dated by effective ex-date."""
import os
from datetime import datetime,timedelta,timezone
URL='https://data.alpaca.markets/v1/corporate-actions'
async def snapshot(session,fetch):
    now=datetime.now(timezone.utc)
    result={'source':URL,'checked_at':now.isoformat(),'lookback_days':30,'events':[],'status':'unverified'}
    key=os.getenv('ALPACA_API_KEY');secret=os.getenv('ALPACA_API_SECRET')
    if not key or not secret:return {**result,'error':'corporate_actions_credentials_missing'}
    # API query uses process_date, so request an extended window and filter ex_date.
    params={'types':'reverse_split','start':(now-timedelta(days=365)).date().isoformat(),'end':now.date().isoformat(),'limit':1000,'data_quality':'all'}
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    tokens=set()
    try:
        while True:
            data=await fetch(session,URL,headers=headers,params=params)
            items=data.get('corporate_actions',{}).get('reverse_splits')
            if not isinstance(items,list):raise ValueError('reverse_split_payload_missing')
            result['events'].extend(items)
            token=data.get('next_page_token')
            if not token:break
            if token in tokens:raise ValueError('repeated_page_token')
            tokens.add(token);params['page_token']=token
        result['status']='ok'
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)[:100]
    return result

def apply(stocks,feed):
    for stock in stocks:
        stock['split_check']={k:v for k,v in feed.items() if k!='events'}
        stock['split_check']['events']=[e for e in feed.get('events',[]) if stock['ticker'] in (e.get('symbol'),e.get('new_symbol'))]
