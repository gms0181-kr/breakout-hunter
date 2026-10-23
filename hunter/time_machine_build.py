"""Build immutable replay bundles from historical Git blobs, not today's listings."""
import base64,concurrent.futures,hashlib,json,os,shutil,subprocess
from pathlib import Path
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
from .squeeze_signals import instant
from .time_machine import run_detection
from .time_machine_evaluate import evaluate

REPO='gms0181-kr/breakout-hunter';OUT=Path('public/time-machine')
MODULES=['core','verification','scope','squeeze_signals','squeeze_discovery','time_machine','time_machine_evaluate']

def fetch(url):
    headers={'User-Agent':'Breakout-Hunter-Time-Machine'}
    if url.startswith('https://api.github.com/') and os.getenv('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers=headers),timeout=60) as r:return json.load(r)
        except Exception:
            if attempt==2:raise RuntimeError('historical_source_fetch_failed') from None

def raw(sha,path):return fetch(f'https://raw.githubusercontent.com/{REPO}/{sha}/public/{path}')
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False))

def envelope(value,at,source,event=None):return {'event_time':event or at,'available_at':at,'retrieved_at':at,'source':source,'value':value}

def normalize(commit,report,cache,series):
    at=commit['commit']['committer']['date'];sha=commit['sha'];source=f'https://github.com/{REPO}/tree/{sha}'
    rows=[];details=report.get('details',{});symbols=cache.get('symbols',{})
    for summary in report.get('observations',[]):
        t=summary['ticker'];detail=details.get(t,{});original=detail.get('stock',{})
        stock={k:v for k,v in summary.items() if k not in ('analysis','float','short_volume','outstanding_fact')}
        for k in ('split_check','halt_check','security_type','industry','china_verified'):
            if k in original:stock[k]=original[k]
        inputs={'stock':envelope(stock,at,source),'observation':envelope(symbols.get(t,detail.get('observation',{})),at,source)}
        bars=[]
        for values in (series.get(t) or [[b.get(k) for k in ('time','open','high','low','close','volume','vwap')] for b in original.get('bars',[]) if b.get('complete') is not False])[-65:]:
            b=dict(zip(('time','open','high','low','close','volume','vwap'),values));dt=instant(b['time'])
            if not dt:continue
            day=dt.astimezone(ZoneInfo('America/New_York')).date()
            # Completed daily bars in stored scan; conservative normal close + commit availability.
            event=datetime.combine(day,time(16),ZoneInfo('America/New_York')).astimezone(timezone.utc)
            if event>instant(at):continue
            b.update(available_at=at,complete=True);bars.append(b)
        inputs['bars']=envelope(bars,at,'Alpaca IEX split-adjusted daily bars archived in '+source)
        if original.get('intraday'):inputs['intraday']=envelope(original['intraday'],at,'Alpaca IEX 5min archived in '+source)
        if original.get('sec'):inputs['sec']=envelope(original['sec'],at,'SEC source-linked documents archived in '+source)
        rows.append({'inputs':inputs,'stored_signal':{'as_of':summary.get('analysis',{}).get('as_of'),'candidate':summary.get('analysis',{}).get('candidate'),'stage':summary.get('analysis',{}).get('stage'),'score':summary.get('analysis',{}).get('observed_score'),'note':'당시 저장 신호 · 현재 엔진 재계산과 구분'}})
    return {'schema_version':2,'source_commit':sha,'event_time':report['updated_at'],'available_at':at,'retrieved_at':at,'source':source,'engine_hash':hashlib.sha256(Path('hunter/squeeze_signals.py').read_bytes()).hexdigest(),'universe_complete':False,'listing_count':len(report.get('universe_audit',{})),'rows':rows}

def build_one(commit):
    sha=commit['sha'];file=OUT/(sha+'.json')
    if not file.exists() or json.loads(file.read_text()).get('schema_version',0)<2:
        report=raw(sha,'squeeze-hunter.json');cache=raw(sha,'squeeze-cache.json')
        letters=sorted({x['ticker'][0] for x in report.get('observations',[])})
        def get(letter):
            try:return raw(sha,'squeeze-series-'+letter+'.json').get('symbols',{})
            except RuntimeError:return {}
        series={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for shard in pool.map(get,letters):series.update(shard)
        write(file,normalize(commit,report,cache,series))
    d=json.loads(file.read_text())
    return {'commit':sha,'available_at':d['available_at'],'file':sha+'.json','stocks':len(d['rows']),'listing_count':d['listing_count'],'usable_price_stocks':sum(len(r['inputs'].get('bars',{}).get('value',[]))>=22 for r in d['rows']),'status':'PARTIAL REPLAY' if any(len(r['inputs'].get('bars',{}).get('value',[]))>=22 for r in d['rows']) else 'NOT REPRODUCIBLE','sha256':hashlib.sha256(file.read_bytes()).hexdigest()}

def future_data(snapshot):
    out={}
    for row in snapshot['rows']:
        inputs=row['inputs'];s=inputs['stock']['value'];bars=[]
        for b in inputs.get('bars',{}).get('value',[]):
            dt=instant(b['time']).astimezone(ZoneInfo('America/New_York'));day=dt.date()
            bars.append({**b,'session_open':datetime.combine(day,time(0,0),ZoneInfo('America/New_York')).isoformat(),'event_time':datetime.combine(day,time(20),ZoneInfo('America/New_York')).isoformat()})
        out[s['ticker']]={'bars':bars,'source':inputs.get('bars',{}).get('source'),'split_events':s.get('split_check',{}).get('events',[]),'price_basis_verified':False,'session_verified':False}
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    commits=fetch(f'https://api.github.com/repos/{REPO}/commits?path=public/squeeze-hunter.json&per_page=100')
    # First/last stored scan per ET calendar day: predeclared, never chosen by returns.
    days={}
    for c in reversed(commits):days.setdefault(c['commit']['committer']['date'][:10],[]).append(c)
    selected=[]
    for group in days.values():selected.extend([group[0],group[-1]])
    selected=list({c['sha']:c for c in selected}.values())[-8:]
    entries=[]
    for c in selected:
        try:entries.append(build_one(c))
        except RuntimeError:print('Archive source unavailable; snapshot excluded',c['sha'])
    entries.sort(key=lambda e:e['available_at'])
    runtime=OUT/'engine';runtime.mkdir(exist_ok=True)
    for module in MODULES:shutil.copyfile('hunter/'+module+'.py',runtime/(module+'.py'))
    write(OUT/'tzdata.json',{zone:base64.b64encode(Path('/usr/share/zoneinfo',zone).read_bytes()).decode() for zone in ('America/New_York','Asia/Seoul')})
    hashes={m:hashlib.sha256((runtime/(m+'.py')).read_bytes()).hexdigest() for m in MODULES}
    write(OUT/'index.json',{'schema_version':1,'built_at':datetime.now(timezone.utc).isoformat(),'snapshots':entries,'engine_modules':MODULES,'engine_hashes':hashes,'limitations':['과거 전체 상장 원자료·중국계 분류 완전성 미검증','당시 CTB·SEC 공개 시각 누락은 추정하지 않음','과거 IEX 병합 조정 기준·실제 체결 가격 재현 미검증']})
    if entries:
        demo_entry=next((e for e in entries if e['status']=='PARTIAL REPLAY'),entries[0])
        first=json.loads((OUT/demo_entry['file']).read_text());last=json.loads((OUT/entries[-1]['file']).read_text())
        replay=run_detection(first,demo_entry['available_at']);outcomes=future_data(last)
        # A later provider adjustment may not be retroactively used for detection.
        # For outcome comparison only, require >=20 identical overlapping OHLCV bars.
        for entry in entries:
            earlier=json.loads((OUT/entry['file']).read_text())
            for row in earlier['rows']:
                t=row['inputs']['stock']['value']['ticker']
                if t not in outcomes:continue
                old={b['time']:b for b in row['inputs'].get('bars',{}).get('value',[])}
                new={b['time']:b for b in outcomes[t]['bars']}
                common=set(old)&set(new)
                same=len(common)>=20 and all(all(abs(old[d][k]-new[d][k])<=max(1e-8,abs(old[d][k])*1e-9) for k in ('open','high','low','close','volume')) for d in common)
                outcomes[t].setdefault('price_basis_by_snapshot',{})[entry['commit']]=same
                outcomes[t]['basis_method']='20개 이상 겹치는 일봉 OHLCV 동일 여부; 성과 평가 전용 · 실제 체결 검증 아님'
        write(OUT/'outcomes.json',{'source_commit':last['source_commit'],'data':outcomes})
        write(OUT/'demo.json',{'detection':replay,'evaluation':evaluate(replay['frozen'],outcomes)})
        # Demo freeze candidates before evaluation and never re-rank on outcome data.
        print(json.dumps({'snapshots':len(entries),'earliest':entries[0]['available_at'],'latest':entries[-1]['available_at'],'examined':replay['examined'],'candidates':replay.get('candidate_count',0),'status':replay['status'],'verified_success_rate':None}))
    else:raise RuntimeError('No reproducible historical archives available')
if __name__=='__main__':main()
