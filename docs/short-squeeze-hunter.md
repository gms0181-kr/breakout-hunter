# SHORT SQUEEZE HUNTER 1.0

Independent scanner: `python -m hunter.squeeze_scan`. No dependency on legacy
candidate lists, engine scores, previous ranks or designated case tickers.

## Universe and collection

Nasdaq Trader listing directories supply NASDAQ, NYSE, NYSE American common
shares / ADS. Nasdaq screener market caps must be verified and at most
2,000,000,000 USD. Price must be positive and below 10 USD; reverse splits in
30 days, funds, ETF/ETN, bonds, preferred, warrants/ADW, rights, units,
investment trusts, REIT/BDC and SPAC are excluded. Delisted names are absent
from the active directory, not assumed tradable. Missing data is counted.

Each run obtains whole scoped-universe split-adjusted Alpaca IEX daily bars.
Public ChartExchange/IBKR borrow, ChartExchange official FINRA SI and
ChartExchange/Finviz float adapters rotate 160 due names per run, oldest or
unseen first. This is not a complete fresh borrow scan every 15 minutes.
A cached shared observation may be reused but legacy candidates are not.
Two concurrent source workers; Fintel denial is reported without bypass.
Historical CTB is retained for 24h/3d/5d comparisons only when a timestamped
baseline exists (12h tolerance before each boundary). 0-share observation
spans cannot establish continuous market-wide unavailability.

Up to 100 names with at least two independently evaluated pressure signals
receive IEX 5-minute bars, with end time 20 minutes behind now. SEC source
and exhibit collection rotates 12 such names per run with a 6-hour cache.
Actual Alpaca calendar defines holidays, early close and ET session state.
UTC weekday cron: `7,22,37,52 * * * 1-5`. Actions scheduling/queue/run time is
not a real-time SLA; actual observation ages appear on screen.

## Observed score

All weights below are explicit in `hunter/squeeze_signals.py`. Missing is
`null`, a confirmed weak signal can be zero, weights are not renormalized.

| Component | Maximum | Rules |
|---|---:|---|
| Short pressure |30|CTB levels 20/50/100/200/400 each +1 (5); 24h rise >=20pp=5, >=5pp=3, >0=1 (5); last 3 observations strictly rising=2; availability 0=3, <=10,000=2, <=100,000=1 (3); decrease >=80%=5, >=50%=3, >0=1 (5); official SI/Float >=20%=6, >=10%=4, >=5%=2 (6); SI report growth >=20%=4, >0=2 (4)|
| Capital inflow context |25|20-day dollar-volume ratio >=2=10, >=1.3=5 only with nonnegative price reaction, low defense and close in upper half; RVOL >=2=5, >=1.2=2 under same hold conditions; close >= daily VWAP with nonnegative return=5; rising OBV with low defense=5|
| Price structure |20|RSI14 simple-average <=35 + rebound + low defense=5, or higher low + defense=2; prior close below prior VWAP then reclaim=5, or above=2; close above previous20 high=5, within5% below=2; five-day range and volume compression plus support=5|
| Dilution gap |20|Only source-backed, timed, reviewed contract assessment may score: confirmed gap20 / low immediate risk12 / high immediate risk0; otherwise missing. Lexical absence never means safe.|
| Catalyst |5|SEC original filing accepted within72h=1; direction unverified. Current adapter does not manufacture FDA/clinical/earnings dates.|

RSI is simple-average RSI14, OBV uses daily direction. Dollar-volume is
close x IEX volume, not consolidated turnover or net cash buying. Official
SI settlement date is not its public release date. Source-provided ratios
above100%, intervening split or ADS/float basis flags block SI scoring.

## State and rank

Recomputed statelessly every run, so jumps and downgrades are allowed:

- Missing latest price or pressure: unconfirmed (no forced DORMANT).
- DORMANT: one observed short-pressure signal.
- FUEL BUILDING: at least two observed pressure signals.
- SETUP: plus above VWAP, low defense and dollar-volume ratio >=1.3.
- IGNITION: plus resistance breakout and ratio >=2.
- EXPANSION: ignition conditions + close retention >=75%, five-day return
  >=15% and positive daily return.

Fresh delayed intraday data takes precedence for current stage; otherwise
completed-day stage is explicitly labeled, not called a live signal.
Current capital/structure **score** uses completed daily bars.
Downgrade occurs on the same conditions becoming false. Previous rank is
never an input. State/history persists separately.

Candidate eligibility needs >=2 pressure signals, valid fresh daily data,
short-pressure covered weight>=8, total covered weight>=45. Research TOP10
also requires current official halt-feed + recent IEX trade evidence.
High reviewed immediate dilution risk is a separate group. Actionable TOP10
additionally requires source-backed low dilution risk and verified Toss
orderability. No connector verifies Toss orderability today; hence this
list may correctly be empty. Research observations are not recommendations.

## Alerts, replay and limitations

Site-internal alerts cover CTB +20pp, borrow decrease>=50%, same-coverage
short-pressure +8 points, stage changes (including down/unconfirmed),
price breakout + turnover, and newly discovered dilution disclosure flags.
Dedup ID is ticker/type/source timestamp. No external message channel is
assumed connected or used.

Separate forward snapshots record actual scan-known timestamps. Replay
uses only subsequently observed daily closes: +10% within five subsequent
observations defines an operational hit. This is neither intraday spike
performance nor executable return. Unmatured cases do not contribute a
false-positive rate. SHFS/INLF/NCPL/SAIL/TNGX remain unverified without
specified event dates and contemporaneous borrow/SEC evidence. No current
CTB is backfilled. Daily prices have provider split adjustments; replay
uses frozen prices and should be treated as blocked across share-basis
changes until those corporate actions are reconciled.

SEC source/exhibit retrieval is implemented; instrument-level legal
issuance/free-resale conclusion remains unverified when conditions cannot
be reconciled. This is a material limitation, not a completed safety check.
Fintel numerical cross-validation, consolidated live tape, classified
buy/sell trade pressure and broad verified future event calendars are not
available. The 3-band chart is a typical-price volume proxy, never actual
short-entry prices or liquidation levels.

Original engines, original workflow schedules and Secrets values are
preserved. No files or settings in `gms0181-kr/surge-radar` are touched.
