import os,unittest
from unittest.mock import AsyncMock,patch
from hunter.providers import collect
class RetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_empty_symbol_is_retried_and_logged(self):
        stocks={s:{"ticker":s,"name":s,"halt_status":"unverified"} for s in ("AAA","BBB")}
        bars={"AAA":[{"time":"2026-10-19T04:00:00Z","close":1,"low":1,"volume":100}]}
        with patch.dict(os.environ,{"ALPACA_API_KEY":"fixture-key","ALPACA_API_SECRET":"fixture-secret"}),patch("hunter.providers.universe",AsyncMock(return_value=(stocks,[]))),patch("hunter.providers.bars",AsyncMock(side_effect=[(bars,[]),({},[])])) as request,patch("hunter.providers.screener_metadata",AsyncMock(return_value=({},[]))),patch("hunter.providers.sec_index",AsyncMock(return_value=({},[]))),patch("hunter.backtest.replay",AsyncMock(return_value={})),patch("hunter.providers.fetch",AsyncMock(return_value={"rates":{"KRW":1000},"date":"2026-10-20"})):
            _,coverage=await collect({"sec_budget":0})
        self.assertEqual(request.await_count,2)
        self.assertEqual(request.await_args_list[1].args[1],["BBB"])
        self.assertTrue(any(f.get("ticker")=="BBB" and f.get("error")=="no_bars_after_retry" for f in coverage["failures"]))
