"""Exchange trading calendar from the existing Alpaca account; no guessed holidays."""
import os
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
async def collect(session):
    now=datetime.now(timezone.utc);date=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    through=(now.astimezone(ZoneInfo('America/New_York')).date()+timedelta(days=7)).isoformat()
    result={'date':date,'through':through,'status':'unverified','checked_at':now.isoformat()}
    key=os.getenv('ALPACA_API_KEY');secret=os.getenv('ALPACA_API_SECRET')
    if not key or not secret:return result
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    for base in ('https://paper-api.alpaca.markets','https://api.alpaca.markets'):
        url=base+'/v2/calendar'
        try:
            import aiohttp
            async with session.get(url,headers=headers,params={'start':date,'end':through},timeout=aiohttp.ClientTimeout(total=12)) as response:
                if response.status==401:continue
                if response.status!=200:return {**result,'source':url,'error':'HTTP '+str(response.status)}
                data=await response.json()
                if not isinstance(data,list):raise ValueError('calendar_schema')
                record=next((x for x in data if x.get('date')==date),None)
                if record and (not record.get('open') or not record.get('close')):raise ValueError('calendar_hours_missing')
                return {**result,'status':'ok','source':url,'sessions':data,'session':record,'is_trading_day':bool(record)}
        except Exception as exc:return {**result,'source':url,'error':type(exc).__name__}
    return {**result,'error':'calendar_auth_unavailable'}

async def standalone():
    import aiohttp
    async with aiohttp.ClientSession() as session:return await collect(session)
