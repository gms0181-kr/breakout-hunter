"""Inspect official public halt sources; no credentials used."""
import json,urllib.request,urllib.error
from pathlib import Path
def main():
    out={}
    for name,url,payload in [
        ("rss","https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts",None),
        ("current","https://www.nasdaqtrader.com/RPCHandler.axd",{"id":2,"method":"BL_TradeHalt.GetTradeHalts","params":"[]","version":"1.1"})
    ]:
        try:
            body=json.dumps(payload).encode() if payload else None
            req=urllib.request.Request(url,data=body,headers={"User-Agent":"BREAKOUT-HUNTER/1.0","Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=40) as response:
                text=response.read().decode("utf-8-sig")
                out[name]={"http":response.status,"date":response.headers.get("Date"),"content_type":response.headers.get("Content-Type"),"body":text}
        except Exception as exc: out[name]={"error":type(exc).__name__,"message":str(exc)}
    Path("public/halt-source-probe.json").write_text(json.dumps(out,ensure_ascii=False))
    print(json.dumps(out,ensure_ascii=False))
if __name__=="__main__":main()
