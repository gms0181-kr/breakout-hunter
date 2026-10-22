import subprocess,unittest
from pathlib import Path
from hunter.short_reports import official_interest,finra_rows
class ShortReportsTests(unittest.TestCase):
    def test_si_table_has_settlement_provenance_and_previous_row(self):
        html='<title>TEST Short Interest</title>Official Data from Finra<table><tr><td>2026-09-30</td><td>12</td><td>1,200</td><td>1.5</td><td>200</td><td>20</td><td>20000</td><td>10000</td></tr><tr><td>2026-09-15</td><td>10</td><td>1,000</td><td>1</td><td>0</td><td>0</td><td>20000</td><td>10000</td></tr></table>'
        r=official_interest(html,'TEST');self.assertEqual(r['shares'],1200);self.assertEqual(r['previous']['shares'],1000);self.assertEqual(r['settlement_date'],'2026-09-30');self.assertFalse(r['cross_verified'])
        self.assertNotIn('shares',official_interest('<title>TEST</title>No data','TEST'))
    def test_finra_volume_has_same_scope_denominator_and_zero_is_valid(self):
        raw='Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20261021|TEST|0|0|1000|B,Q,N\n20261021|BAD|2000|0|1000|B,Q,N\n'
        r=finra_rows(raw,'20261021');self.assertEqual(r['TEST']['ratio_pct'],0);self.assertEqual(r['TEST']['total_volume'],1000);self.assertNotIn('BAD',r)
        with self.assertRaises(ValueError):finra_rows('wrong','20261021')
    def test_javascript_engine_regressions(self):
        result=subprocess.run(['node','--test','tests/short-pressure.test.js'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
