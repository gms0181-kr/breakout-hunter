"""Evidence discovery only; lexical mentions never certify issuance or legal resale."""
import asyncio, re, hashlib, os
from .providers import fetch
PATTERNS={
 "ATM":r"at.the.market|equity distribution agreement",
 "SHELF":r"shelf registration",
 "PIPE":r"private investment in public equity|private placement",
 "ELOC":r"equity line|equity purchase agreement|standby equity",
 "CONVERTIBLE":r"convertible (?:note|debenture|preferred)",
 "WARRANT":r"warrants?",
 "PRE_FUNDED":r"pre.funded",
 "RESALE":r"resale|selling shareholders?|selling stockholders?",
 "LOCKUP":r"lock.up",
 "BLOCKER_9_99":r"9\.99\s*%",
 "RESET":r"price reset|downward adjustment|anti.dilution",
 "CLOSING":r"closing|closed",
 "REGISTRATION":r"registration statement",
 "RULE_144":r"rule 144",
}
STAGES=["계약 체결","발행 승인","실제 증권 발행","전환/행사 가능","실제 전환/행사","보통주 발행","자유매도 가능","실제 시장 매도"]

async def analyze(session,cik,sec,budget=3):
    agent=os.getenv("SEC_USER_AGENT")
    output={**sec,"reviewed":False,"coverage_complete":False,"immediately_sellable":None,"analysis_method":"원문/첨부 키워드 탐색; 법적 공급 상태 미확정","supply_stages":[{"stage":s,"status":"미확인"} for s in STAGES],"documents":[],"risk_flags":[]}
    if not agent: return output
    seen=set()
    for filing in (sec.get("timeline") or [])[:budget]:
        urls=[filing["source"]]
        try:
            index_url=filing["source"].rsplit("/",1)[0]+"/index.json"
            directory=await fetch(session,index_url,headers={"User-Agent":agent})
            attachments=[i["name"] for i in directory.get("directory",{}).get("item",[]) if re.search(r"(ex10|ex99|ex4|exhibit)",i.get("name",""),re.I) and i.get("name","").endswith((".htm",".html",".txt"))]
            urls += [index_url.rsplit("/",1)[0]+"/"+name for name in attachments[:8]]
        except RuntimeError:
            output["attachment_status"]="첨부 목록 접근 실패; 검토 미완료"
        for url in urls:
            if url in seen: continue
            seen.add(url)
            try:
                html=await fetch(session,url,headers={"User-Agent":agent},text=True)
                plain=re.sub(r"<[^>]+>"," ",re.sub(r"<(script|style).*?</\1>"," ",html,flags=re.S|re.I))
                flags=[name for name,pattern in PATTERNS.items() if re.search(pattern,plain,re.I)]
                output["documents"].append({"source":url,"filed":filing["filed"],"form":filing["form"],"flags":flags,"sha256":hashlib.sha256(html.encode()).hexdigest(),"status":"문구 탐지; 수량/발행/자유매도 확정 아님"})
                output["risk_flags"]=sorted(set(output["risk_flags"]+flags))
            except RuntimeError:
                output["documents"].append({"source":url,"status":"접근 실패; 미확인"})
            await asyncio.sleep(.25)
    output["status"]="잠재 희석 관련 문구 발견; 현재 공급 미확인" if output["risk_flags"] else "검토 범위 내 문구 미탐지; 희석 공백 확인 아님"
    output["blocker_note"]="9.99(%) blocker는 보유 제한이며 누적 발행 상한이 아님"
    return output

async def outstanding_fact(session,cik,as_of):
    agent=os.getenv("SEC_USER_AGENT")
    if not agent: return None
    url=f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/dei/EntityCommonStockSharesOutstanding.json"
    try:
        data=await fetch(session,url,headers={"User-Agent":agent})
        facts=[x for x in data.get("units",{}).get("shares",[]) if x.get("filed","9999")<=as_of[:10] and x.get("end","9999")<=as_of[:10] and x.get("val",0)>0]
        if not facts: return None
        fact=max(facts,key=lambda x:(x.get("end",""),x.get("filed","")))
        return {"value":fact["val"],"as_of":fact["end"],"filed":fact["filed"],"source":url,"basis":"reported outstanding; split reconciliation pending"}
    except RuntimeError: return None
