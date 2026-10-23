"""Authenticated job orchestration wrapper; reuse the existing reconstruction."""
import argparse,asyncio,json,os,uuid
from datetime import datetime,timezone
import aiohttp
from .time_machine import et_instant
from .time_machine_reconstruct import Client,reconstruct,save_reconstruction

def validate_job(request_id,et,scope,now=None):
    identifier=str(uuid.UUID(request_id))
    if identifier!=request_id.lower():raise ValueError('UUID 형식 오류')
    cutoff=et_instant(et)
    if cutoff>=(now or datetime.now(timezone.utc)):raise ValueError('과거 시각만 실행 가능')
    if scope not in ('all','china'):raise ValueError('지원하지 않는 범위')
    return identifier,cutoff

async def execute(request_id,et,scope,client):
    identifier,cutoff=validate_job(request_id,et,scope)
    result=await reconstruct(client,cutoff,scope)
    result['job']={'id':identifier,'et':et,'scope':scope,'github_run_id':os.getenv('GITHUB_RUN_ID'),'cache_reused':False}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--request-id',required=True);p.add_argument('--et',required=True);p.add_argument('--scope',choices=['all','china'],default='all');args=p.parse_args()
    identifier,_=validate_job(args.request_id,args.et,args.scope)
    key=os.getenv('ALPACA_API_KEY');secret=os.getenv('ALPACA_API_SECRET')
    if not key or not secret:raise ValueError('기존 Alpaca Secrets 미설정; 값은 출력하지 않음')
    async def run():
        async with aiohttp.ClientSession() as session:return await execute(identifier,args.et,args.scope,Client(session,key,secret))
    result=asyncio.run(run());output='public/time-machine/jobs/'+identifier+'.json';save_reconstruction(result,output)
    print(json.dumps({'job':result['job'],'as_of':result['as_of'],'status':result['result']['status'],'analysis_stocks':result['result']['examined'],'usable_daily':result['result']['usable_price_stocks'],'candidate_count':result['result']['candidate_count'],'top20_count':len(result['result']['top20']),'api_requests':result['result']['coverage_report']['api_requests'],'output':output},ensure_ascii=False))

if __name__=='__main__':main()
