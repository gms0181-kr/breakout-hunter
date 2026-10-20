"""Public float / borrow source response diagnostic; no paid data or credentials."""
import json,urllib.request
from pathlib import Path
def main():
    out={}
    for label,url in [
      ("overview","https://chartexchange.com/symbol/nasdaq-prso/"),
      ("borrow","https://chartexchange.com/symbol/nasdaq-prso/borrow-fee/"),
      ("finviz","https://finviz.com/quote.ashx?t=PRSO"),
      ("fintel","https://fintel.io/ss/us/prso")
    ]:
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"BREAKOUT-HUNTER/1.0"})
            with urllib.request.urlopen(req,timeout=25) as res:
                text=res.read().decode("utf-8")
                out[label]={"url":url,"http":res.status,"body":text}
        except Exception as exc:out[label]={"url":url,"error":type(exc).__name__,"message":str(exc)}
    Path("public/float-ctb-probe.json").write_text(json.dumps(out))
    print(json.dumps({k:{a:b for a,b in v.items() if a!="body"} for k,v in out.items()}))
if __name__=="__main__":main()
