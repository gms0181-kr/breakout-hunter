"""Index completed external jobs for lookup only; never select or score stocks."""
import hashlib,json,uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]

def build_index(public,engine_hash):
    jobs=[];rejected=0
    for path in sorted((Path(public)/'time-machine/jobs').glob('*.json')):
        try:
            report=json.loads(path.read_text());job=report['job'];result=report['result']
            assert str(uuid.UUID(job['id']))==path.stem==job['id']
            stamp=datetime.fromisoformat(report['as_of'].replace('Z','+00:00'))
            assert stamp.tzinfo and stamp.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%dT%H:%M')==job['et']
            assert job['scope'] in ('all','china') and result['mode']==job['scope']
            assert result['engine_hash']==engine_hash and result['acquisition_mode']=='HISTORICAL RECONSTRUCTION'
            assert isinstance(result['top20'],list) and len(result['top20'])<=20
            retrieved=datetime.fromisoformat(report['retrieved_at'].replace('Z','+00:00'));assert retrieved.tzinfo
            jobs.append({'id':job['id'],'et':job['et'],'scope':job['scope'],'as_of':report['as_of'],'retrieved_at':report['retrieved_at'],'status':result['status'],'top20_count':len(result['top20']),'path':'./time-machine/jobs/'+path.name})
        except (AssertionError,ValueError,KeyError,TypeError,json.JSONDecodeError):rejected+=1
    jobs.sort(key=lambda j:j['retrieved_at'],reverse=True)
    return {'schema':1,'engine_hash':engine_hash,'jobs':jobs,'rejected_reports':rejected,'purpose':'Completed external collection lookup; cache reuse, never a new collection'}

if __name__=='__main__':
    index=build_index(ROOT/'public',hashlib.sha256((ROOT/'hunter/squeeze_signals.py').read_bytes()).hexdigest())
    output=ROOT/'public/time-machine/completed-jobs.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')))
    print('Completed external jobs indexed:',len(index['jobs']),'rejected:',index['rejected_reports'])
