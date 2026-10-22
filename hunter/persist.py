"""Persist generated JSON onto latest main; retry non-fast-forward without force.
Only runs in this repository's disposable GitHub Actions checkout.
"""
import json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
MODES={'scan':['public/data.json','public/hubc-backtest.json','public/connections.json','public/halts.json','public/enrichment.json'],'halts':['public/data.json','public/halts.json'],'enrichment':['public/enrichment.json']}

def stamp(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.timestamp() if d.tzinfo else -1
    except (ValueError,TypeError):return -1

def report_key(d):return stamp(d.get('updated_at')),stamp(d.get('ranking_updated_at'))
def merge_enrichment(a,b):
    out=dict(max((a,b),key=lambda d:stamp(d.get('updated_at'))));symbols={}
    for ticker in set(a.get('symbols',{}))|set(b.get('symbols',{})):
        x=a.get('symbols',{}).get(ticker,{});y=b.get('symbols',{}).get(ticker,{})
        current=dict(max((x,y),key=lambda d:stamp(d.get('observed_at'))))
        history={h.get('as_of'):h for d in (x,y) for h in d.get('borrow_history',[]) if h.get('as_of')}
        current['borrow_history']=sorted(history.values(),key=lambda d:stamp(d.get('as_of')))[-240:]
        symbols[ticker]=current
    out['symbols']=symbols;return out

def choose(path,remote,incoming):
    if remote is None:return incoming
    if path=='public/data.json':return incoming if report_key(incoming)>report_key(remote) else remote
    if path=='public/halts.json':key='checked_at'
    elif path=='public/connections.json':key='tested_at'
    elif path=='public/enrichment.json':return merge_enrichment(remote,incoming)
    else:return incoming
    return incoming if stamp(incoming.get(key))>stamp(remote.get(key)) else remote

def git(*args,ok=(0,)):
    result=subprocess.run(['git',*args],capture_output=True,text=True)
    if result.returncode not in ok:raise RuntimeError('git_'+args[0]+'_failed')
    return result

def main(mode):
    if os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('GITHUB_REPOSITORY')!='gms0181-kr/breakout-hunter':raise RuntimeError('disposable_actions_checkout_required')
    paths=MODES[mode];snapshot={p:json.loads(Path(p).read_text()) for p in paths if Path(p).exists()}
    git('config','user.name','breakout-hunter-bot');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    for attempt in range(5):
        git('fetch','origin','main');git('reset','--hard','origin/main')
        selected_data=False
        for p,new in snapshot.items():
            try:remote=json.loads(Path(p).read_text())
            except (OSError,ValueError):remote=None
            value=choose(p,remote,new)
            if p=='public/data.json':selected_data=value is new
            if p=='public/hubc-backtest.json' and not selected_data:continue
            Path(p).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
        git('add',*snapshot)
        if git('diff','--cached','--quiet',ok=(0,1)).returncode==0:print('Latest observations already persisted');return
        git('commit','-m','Persist '+mode+' observations with timestamp reconciliation [skip ci]')
        push=git('push','origin','HEAD:main',ok=(0,1))
        if push.returncode==0:print('Persisted '+mode+' observations');return
        time.sleep(1+attempt)
    raise RuntimeError('persistence_retry_exhausted')

if __name__=='__main__':main(sys.argv[1])
