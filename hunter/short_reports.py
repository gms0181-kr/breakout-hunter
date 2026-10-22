"""Provenance-preserving official SI redistribution and FINRA daily volume."""
import csv,io,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

def official_interest(html,ticker):
    from .float_ctb import identity,plain
    identity(html,ticker)
    if 'Data from Finra' not in plain(html) or 'Official' not in plain(html):return {'status':'official_source_unconfirmed'}
    rows=[]
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>',html,re.S|re.I):
        cells=[plain(x) for x in re.findall(r'<td\b[^>]*>(.*?)</td>',tr,re.S|re.I)]
        if len(cells)<8 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',cells[0]):continue
        try:
            v=[float(x.replace(',','').replace('+','')) for x in cells[1:8]]
            if any(x<0 for x in [v[0],v[1],v[2],v[5],v[6]]):continue
            rows.append({'settlement_date':cells[0],'float_pct':v[0],'shares':int(v[1]),'days_to_cover':v[2],'change_shares':v[3],'change_pct':v[4],'outstanding_reference':v[5],'float_reference':v[6]})
        except ValueError:continue
    rows.sort(key=lambda x:x['settlement_date'],reverse=True)
    if not rows:return {'status':'official_rows_unavailable'}
    return {**rows[0],'previous':rows[1] if len(rows)>1 else None,'history':rows[:12],'status':'source_reported_official','official_origin':'FINRA','basis_note':'ChartExchange 제공 병합·분할 조정 과거값; 현재 Float와 직접 혼합하지 않음','cross_verified':False}

def finra_rows(raw,date):
    rows={}
    if not raw.startswith('Date|Symbol|ShortVolume|'):raise ValueError('finra_header_mismatch')
    for row in csv.DictReader(io.StringIO(raw),delimiter='|'):
        try:
            if row.get('Date')!=date:continue
            short=int(row['ShortVolume']);total=int(row['TotalVolume']);exempt=int(row['ShortExemptVolume'])
            if total<=0 or not 0<=short<=total or not 0<=exempt<=short:continue
            rows[row['Symbol']]={'short_volume':short,'total_volume':total,'short_exempt_volume':exempt,'ratio_pct':100*short/total,'date':datetime.strptime(date,'%Y%m%d').date().isoformat(),'scope':'FINRA CNMS/TRF·ADF 보고 범위; 전 거래소 통합 거래량 아님','status':'source_reported','provider':'FINRA CNMS'}
        except (ValueError,TypeError,KeyError):continue
    if not rows:raise ValueError('finra_rows_empty')
    return rows

def latest_finra(get,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/New_York'))
    first=now.date() if now.hour>=17 else (now-timedelta(days=1)).date()
    attempts=[]
    for offset in range(7):
        date=first-timedelta(days=offset)
        if date.weekday()>4:continue
        stamp=date.strftime('%Y%m%d');url='https://cdn.finra.org/equity/regsho/daily/CNMSshvol'+stamp+'.txt'
        try:
            rows=finra_rows(get(url),stamp)
            observed=datetime.now(timezone.utc).isoformat()
            return {t:{**r,'source':url,'observed_at':observed} for t,r in rows.items()},{'status':'ok','source':url,'date':date.isoformat(),'observed_at':observed}
        except Exception as exc:
            attempts.append({'date':date.isoformat(),'error':type(exc).__name__})
            # Stop after a provider security denial; do not probe alternate paths.
            if getattr(exc,'code',None) in (401,403,429):break
    return {},{'status':'unavailable','attempts':attempts}
