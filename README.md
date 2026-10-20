# BREAKOUT HUNTER 1.0

Independent repository: https://github.com/gms0181-kr/breakout-hunter
Published dashboard: https://gms0181-kr.github.io/breakout-hunter/
Surge Radar repository, data, hosting and settings are outside this project's modification scope.

## Verified collection — 2026-10-20 17:55:33 UTC / 2026-10-21 02:55:33 KST
- Alpaca IEX bars, SEC submissions and SEC ticker index: HTTP 200. No credential values are persisted in public results.
- Complete directory request universe: 5,713 securities after conservative security-name/ETF filtering.
- Price histories returned: 5,710. Three symbols returned no history; subsequent scans retry and explicitly record no-bars responses.
- V scores available: 5,627; R scores: 5,631.
- Nasdaq screener market-cap metadata returned: 6,986 records, joined by ticker.
- SEC enrichment: 19 candidates, 77 original/attachment documents retrieved and hashed.
- SEC keywords indicate potential risk, never proof of legal issuance or market sale.
- Float / licensed borrow and short-interest feeds unavailable: F and S remain null on this run.
- Research TOP 10 generated from real V/R observations and current market-cap metadata, with 40(%) component coverage.
- Actionable TOP 10 withheld: Toss orderability and halt status are unverified.
- FX: daily USD/KRW reference rate from Frankfurter, not an executable or live exchange rate.
- HUBC: four historical regular-session IEX minute reconstructions stored. Split reconciliation, consolidated volume, historic float/short snapshots and historic all-market ranks remain unavailable; detection scores/ranks are not invented.

## Run
Python 3.12+
~~~sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m hunter.probe
python -m hunter.run
python -m http.server 8000 --directory public
~~~

## Configuration / credentials
GitHub Actions secrets: ALPACA_API_KEY, ALPACA_API_SECRET, SEC_USER_AGENT (organization and contact email).
Never print credential values. Connection probes log only provider status, HTTP code and record counts.
Market-cap threshold, SEC enrichment budget and evidence-based Toss orderability overrides are in config.json.
The dashboard's cap input filters displayed rows; it does not modify server configuration.

## Methods and limits
NASDAQ Trader supplies the complete listing directory. Security-type filtering is name-based and requires exception auditing.
IEX-only split-adjusted daily bars are not consolidated market volume or real-time quotes. Missing data is null.
V/F/S/R operate independently; no historic-recommendation bonus.
Exact formulas are in hunter/core.py and the dashboard. Observed points are not renormalized to 100; component coverage is shown.
Reported outstanding shares remain separate from float and retain SEC fact dates. Unreconciled split adjustments are disclosed.
SEC analysis discovers forms, original documents, selected attachments and potential financing clauses. It does not yet reconcile all security IDs, remaining warrant balances, blockers, closing conditions or legal free-sale dates.
All eight supply stages stay unconfirmed without reviewed evidence. No keyword or absent filing earns a dilution-gap score.
HUBC raw minute data ends strictly before 16:00 ET. Future filings are withheld; certified point-in-time replay is incomplete.

## Automatic refresh / persistence
- GitHub Actions scheduled collection: 22:37 UTC Monday–Friday (07:37 KST next day). A scheduled event has not yet been observed; schedules can be delayed.
- Source changes to the scanner also trigger collection. Stale runs are cancelled.
- Results commit to public JSON; SQLite evidence is retained as an Actions artifact. Historical snapshots are not a licensed full-market point-in-time database.
- Dashboard polls stored JSON every 60 seconds. This does not make upstream IEX daily data real-time.
- Successful collection triggers independent GitHub Pages deployment.

## QA
Software tests cover volume baselines, missingness, splits, float/O/S separation, short-volume separation, supply evidence gates, duplicate stages, point-in-time guards, scan-order diversity, ranking, independent short components and retry failures.
Production browser QA checks desktop and mobile layout, actual JSON loading, JavaScript errors and detail opening; production verification additionally waits for an actual automatic data request.
See Actions run conclusions and artifacts for executed test counts and screenshots. These software tests are not a certified historical strategy backtest.

## Incomplete
Verified Float, licensed ChartExchange/Fintel CTB/borrow/short interest, all-stage SEC legal supply reconciliation, verified Toss orderability, current halt-state validation, complete HUBC point-in-time ranks, success/failure comparison cases, and intraday consolidated-price coverage.
