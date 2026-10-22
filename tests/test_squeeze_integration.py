"""Cross-language contract: Python's single engine is consumed without rescoring."""
import json,subprocess,unittest
from tests.test_squeeze_hunter import fixture,NOW
from hunter.squeeze_signals import analyze
class SharedSnapshotTests(unittest.TestCase):
    def test_python_score_source_and_timestamp_round_trip_to_shared_store(self):
        stock,obs=fixture();analysis=analyze(stock,obs,NOW);at=NOW.isoformat()
        row={'ticker':stock['ticker'],'name':'Contract fixture','price':stock['bars'][-1]['close'],'analysis':analysis}
        packet={'schema_version':2,'engine':'SHORT SQUEEZE HUNTER 1.0','snapshot_id':at,'updated_at':at,'observations':[row],'research_top10':[row],'top10':[],'high_risk':[],'details':{stock['ticker']:{'stock':stock,'observation':obs,'analysis':analysis}},'monitor':{'updated_at':at,'history':[],'alerts':[]}}
        script="const fs=require('fs'),assert=require('node:assert/strict'),{normalize}=require('./public/squeeze-store.js');const raw=JSON.parse(fs.readFileSync(0,'utf8')),d=normalize(raw,Date.parse(raw.updated_at));assert.strictEqual(d.research_top10[0].analysis,d.observations[0].analysis);assert.strictEqual(d.details.TEST.analysis,d.observations[0].analysis);console.log(JSON.stringify(d.observations[0].analysis));"
        result=subprocess.run(['node','-e',script],input=json.dumps(packet),capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        consumed=json.loads(result.stdout);self.assertEqual(consumed,analysis)
        self.assertEqual(consumed['ctb']['available_delta'],-100000)
        self.assertEqual(consumed['ctb']['history_24h'][-1],[at,100])
if __name__=='__main__':unittest.main()
