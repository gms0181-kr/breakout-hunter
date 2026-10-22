import unittest
from datetime import datetime,timedelta,timezone
from hunter.halts import parse_feed,classify,eligible

NOW=datetime(2026,10,20,19,0,tzinfo=timezone.utc)
def rss(items="",count=0):
    return f'<rss xmlns:ndaq="http://www.nasdaqtrader.com/"><channel><title>NASDAQTrader.com</title><pubDate>Tue, 20 Oct 2026 19:00:00 GMT</pubDate><ndaq:numItems>{count}</ndaq:numItems>{items}</channel></rss>'
def item(symbol="TEST",halt="14:00:00",resume="",date="10/20/2026"):
    return f'<item><ndaq:IssueSymbol>{symbol}</ndaq:IssueSymbol><ndaq:HaltDate>{date}</ndaq:HaltDate><ndaq:HaltTime>{halt}</ndaq:HaltTime><ndaq:ReasonCode>T1</ndaq:ReasonCode><ndaq:ResumptionDate>10/20/2026</ndaq:ResumptionDate><ndaq:ResumptionTradeTime>{resume}</ndaq:ResumptionTradeTime></item>'
def feed(items="",count=0):
    return parse_feed(rss(items,count),NOW,"Tue, 20 Oct 2026 19:00:00 GMT")
def trade(time="2026-10-20T18:59:00Z"):
    return {"t":time,"p":5.0}
class HaltTests(unittest.TestCase):
    def test_fresh_feed_and_recent_trade(self):
        result=classify("TEST",feed(),trade(),NOW)
        self.assertEqual(result["status"],"no_halt_detected")
        self.assertNotEqual(result["status"],"trading")
    def test_missing_trade_never_clears_long_term_halt(self):
        self.assertEqual(classify("TEST",feed(),None,NOW)["status"],"unverified")
        f=feed(item(date="02/22/2019"),1)
        self.assertEqual(classify("TEST",f,trade(),NOW)["status"],"halted")
    def test_resume_requires_post_resume_trade(self):
        f=feed(item(resume="14:55:00"),1)
        self.assertEqual(classify("TEST",f,trade("2026-10-20T18:54:00Z"),NOW)["status"],"unverified")
        self.assertEqual(classify("TEST",f,trade(),NOW)["status"],"resumed")
    def test_future_resume_stays_halted(self):
        f=feed(item(resume="15:05:00"),1)
        self.assertEqual(classify("TEST",f,trade(),NOW)["status"],"halted")
    def test_latest_rehalt_overrides_previous_resume(self):
        f=feed(item(resume="14:05:00")+item(halt="14:58:00"),2)
        self.assertEqual(classify("TEST",f,trade(),NOW)["status"],"halted")
    def test_stale_or_future_trade(self):
        for time in ("2026-10-20T18:00:00Z","2026-10-20T19:01:00Z"):
            self.assertEqual(classify("TEST",feed(),trade(time),NOW)["status"],"unverified")
    def test_expired_snapshot(self):
        self.assertEqual(classify("TEST",feed(),trade(),NOW+timedelta(minutes=11))["status"],"unverified")
    def test_stale_feed_rejected(self):
        with self.assertRaises(ValueError):
            parse_feed(rss(),NOW+timedelta(minutes=11),"Tue, 20 Oct 2026 19:11:00 GMT")
    def test_partial_feed_or_html_rejected(self):
        for text in (rss(count=2),"<html>blocked</html>"):
            with self.assertRaises(ValueError):parse_feed(text,NOW,"Tue, 20 Oct 2026 19:00:00 GMT")
    def test_dst_conversion_and_milliseconds(self):
        f=feed(item(halt="14:00:00.123"),1)
        self.assertEqual(f["events"][0]["halted_at"],"2026-10-20T18:00:00.123000+00:00")
    def test_cap_and_halt_evidence_gate_without_toss(self):
        check=classify("TEST",feed(),trade(),NOW)
        s={"price":1,"market_cap":1000000,"halt_status":check["status"],"halt_check":check,"toss_orderable":None}
        self.assertTrue(eligible(s,2000000000,NOW))
        for cap in (None,0,-1,3000000000):
            self.assertFalse(eligible({**s,"market_cap":cap},2000000000,NOW))
        self.assertFalse(eligible({**s,"halt_status":"halted"},2000000000,NOW))
        self.assertFalse(eligible(s,2000000000,NOW+timedelta(minutes=11)))
if __name__=="__main__":unittest.main()

