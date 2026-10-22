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
- Actionable TOP 10 withheld: halt status is unverified. Toss orderability is excluded from ranking by user instruction; broker purchase availability is checked by the user.
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
Market-cap threshold and SEC enrichment budget are in config.json. Legacy Toss orderability metadata is retained for reference only and does not gate ranking.
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
Verified Float, licensed ChartExchange/Fintel CTB/borrow/short interest, all-stage SEC legal supply reconciliation, current halt-state validation, complete HUBC point-in-time ranks, success/failure comparison cases, and intraday consolidated-price coverage.

## Halt checks and actionable candidates
Nasdaq official current halt RSS is parsed with item-count, schema, publication-time and HTTP-date checks. A missing symbol is labeled no_halt_detected, never guaranteed trading. Candidates also require a recent IEX latest trade within 15 minutes; a scheduled resumption requires a trade after the scheduled time. Missing/failed/stale sources remain unverified. Positive eligibility expires after at most 10 minutes from RSS publication, or earlier when trade evidence expires. Float, borrow and full SEC supply analysis remain incomplete and never earn assumed points. Toss orderability is user-managed.
A lightweight halt refresh runs on a best-effort 5-minute weekday schedule (12–23 UTC), reranking stored candidate lists without changing original price-scan time; full collection reranks the full universe. GitHub schedules can be delayed. The UI hides expired actionable candidates. Official feed requests are no more frequent than once per process run, and fresh cached snapshots avoid duplicate requests within one minute.



## Independent triple verification (30 / 25 / 40 / 5)
`hunter/verification.py` runs alongside the original V/F/S/R scores. The existing ranking formula is unchanged; `verification_candidates` separately retains stocks passing both market branches, including those absent from legacy signals. SEC enrichment prioritizes joint market signals within the disclosed budget; INLF is an additional case, never a ranking bonus.

Capital: close × volume turnover proxy (4/6/8 points at 2/3/5× the prior 20 completed bars), provider VWAP position/reclaim (3/6), OBV five-bar rise (5), price retention AFTER a prior volume burst (5), post-drop dry volume/floor defense (4), classified buy pressure (2, unavailable until connected). Capital confirmation requires ≥14 points, turnover ≥2× and two non-volume confirmations. This is IEX-only circumstantial evidence, not net inflow. Missing inputs earn no points and reduce available coverage; no normalization.

Structure: the higher of SUPPORT and OVERSOLD (not their sum), five checks ×5 points. SUPPORT requires repeated lows, intact support, ≥15 points and support volume/higher lows/VWAP reclaim. OVERSOLD requires RSI≤30 within four bars, a ≥20% drawdown plus narrow four-bar base, early rebound volume or price recovery and ≥15 points. Daily structures are not intraday entries. Only completed daily bars with available_at≤cutoff participate. Current provider split adjustments are not certified historical point-in-time data.

Dilution: 40 only for a reviewed, time-valid, complete instrument-by-instrument supply reconciliation with SEC document hashes, evidence, stable security IDs, verified post-split share basis and explicit false new-issuance/free-sale states. Confirmed immediate issuance or free sale earns 0 independently of the total score. Unknown is null, not safe. ATM/ELOC/PIPE/RD/Shelf/Resale/warrants/convertibles require coverage. SEC scanning retains original/attachment URLs, timestamps, hashes, clauses and numerical terms, but automatic text extraction does not claim legal reconciliation. **No current automatic source has supplied a fully reviewed legal supply ledger; A grades cannot be inferred from keyword absence or closing announcements.**

Short: five independent one-point metrics (CTB≥30%, zero availability, positive official interest, rising interest, short-volume ratio≥0.5). Each requires ChartExchange/Fintel values agreeing within 5%, timestamps within one hour, dated observation and settlement times; official interest/change also require official attribution. Borrow is fresh for two days, interest for 45 days. CTB/zero availability do not certify a squeeze; short volume is not short interest. Public Fintel denial remains visible. New source snapshots retain actual borrow history for prospective comparisons, never backfilled history.

A: confirmed capital + either structure + reviewed low immediate supply. B: both market conditions, SEC documents present but supply still unresolved. C: both market conditions and confirmed immediate supply risk. Missing core records -> verification unavailable. Otherwise observational, not a qualified grade. Total and independent dilution state appear in table cards and detail views on desktop/mobile.

INLF: `hunter/inlf_case.py` reconstructs the five most recent completed sessions at fixed 15:55 ET cutoffs, excludes minute bars ending after cutoff and later accepted filings, and records raw IEX price/volume/VWAP. The spike date was not specified. Matched-time turnover baselines, historic split reconciliation, historical borrow snapshots and legal supply ledger are absent, so pre-spike detection/rank and unverified metrics stay null. This is an explicit validation limit, not a successful backtest. Current public CTB is not inserted into those historical rows.
