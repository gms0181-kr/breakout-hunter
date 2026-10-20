# BREAKOUT HUNTER 1.0

Independent development in gms0181-kr/breakout-hunter. Never modifies Surge Radar.

## Status
Initial implementation, NOT a completed production system. Execution and deployment must be verified separately.
The dashboard deliberately has no simulated prices, CTB, float, TOP 10, or historical detection results.

## Run
Python 3.12+
~~~sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m hunter.run
python -m http.server 8000 --directory public
~~~

## Data
NASDAQ Trader official complete listing files feed the universe. Name-based security filtering is conservative and requires exception review.
Alpaca credentials provide split-adjusted **IEX-only** daily bars; this is not consolidated volume and cannot validate a consolidated-volume HUBC claim.
Configure repository secrets ALPACA_API_KEY, ALPACA_API_SECRET, SEC_USER_AGENT (organization + contact email).
No credentials are stored in source. No paid signup is performed automatically.
ChartExchange/Fintel licensed CTB, borrow availability, short interest, verified float and FX remain disconnected.

SEC adapter collects filing metadata and original-document links at a conservative rate.
It does NOT yet parse attachments or determine legal free-sale dates, and never labels the absence of a filing as a dilution gap.
The scoring boundary requires explicit reviewed evidence and complete supply coverage for a gap score.
Ownership blockers are not supply caps. Registration is not issuance, exercise, or market sale.

## Scoring / eligibility
See hunter/core.py and the dashboard for exact component formulas.
Unknown components are null, confidence is the sum of observed component weights, and raw known points are not renormalized.
V/F/S/R qualify independently. No historical-recommendation bonus.
Market cap and active-trading eligibility remain unconnected: final TOP 10 is withheld.
Verified Toss orderability is also required for the actionable TOP 10; the pending watchlist is separate.
The market cap limit is in config.json. UI changes filter current observed rows only, not server configuration.

## Scheduling / persistence
GitHub Actions attempts daily 22:37 UTC weekday scans (18:37 EDT / 07:37 KST next day; ET changes with DST).
Actions schedules can be delayed; this is not a real-time SLA. The page polls saved JSON every 60 seconds.
Observed coverage, errors and retry failures are published; SQLite snapshots are retained in workflow artifacts.
SEC secondary review budget is shown independently; partial scans are never labeled comprehensive.
There is no connected hosting deployment yet.

## Tests and limitations
17 unit tests cover averages, missingness, splits, float/O/S, short volume, supply stages, deduplication, point-in-time filters, order diversity, independent engines, rankings and a HUBC claim fixture.
These are software unit tests, not a completed historical HUBC replay or a certified full-universe scanner test.
HUBC 2026-10-12/14/16/19 historical snapshots and comparison success/failure cases remain unavailable. No detection time or rank is invented.
No browser/device or deployed-URL test has been performed.
