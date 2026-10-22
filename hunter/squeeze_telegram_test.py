"""Manual connection test. No fabricated market signal or public credentials."""
import json,sys
from datetime import datetime,timezone
from .squeeze_telegram import deliver_telegram

def main():
    now=datetime.now(timezone.utc)
    a={'id':'telegram-test|'+now.isoformat(),'ticker':'TEST','kind':'connection_test','occurred_at':now.isoformat(),'source_at':now.isoformat(),'previous':None,'current':'연결 테스트','evidence':'실제 종목 신호가 아닌 사용자가 실행한 연결 확인 메시지입니다.'}
    result=deliver_telegram([a],{},now)
    print(json.dumps({k:result[k] for k in ('status','note','accepted_this_run','failed_this_run')},ensure_ascii=False))
    return 0 if result['status']=='telegram_api_accepted' else 1
if __name__=='__main__':sys.exit(main())
