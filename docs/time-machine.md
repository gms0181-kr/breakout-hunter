# TIME MACHINE — independent point-in-time research

Two modes are separate: ARCHIVE REPLAY reuses saved inputs; HISTORICAL RECONSTRUCTION re-collects external historical prices with incomplete-universe reporting. Neither is claimed to be a full historical market reconstruction.

## ARCHIVE REPLAY

Open `time-machine.html` from the website menu. Choose an ET local date, minute and universe; run the existing Python `squeeze_signals.analyze` in an isolated browser worker. Pyodide is loaded on first use. The exact engine files and historical input bundles are SHA-256 checked before execution. No API credentials, Telegram sender or live collector is loaded.

The archive builder selects the first and last stored scan of each available UTC archive day, up to eight snapshots from the latest 100 scan-data commits. This sampling rule is fixed without reading future returns. It is a sparse archive, not every minute's complete market. The most recent snapshot saved at or before the requested instant is selected; age and missing inputs remain visible. The current engine runs at the requested instant, with unchanged weights and thresholds. The scan-time stored signal is separately retained for comparison. It is not assumed to be the current engine's historical decision.

Each input has event_time, available_at, retrieved_at and source. Legacy Git commits provide a conservative latest-known bound: the commit timestamp is used as availability/retrieval, never the historical price date or SEC settlement date. Data first saved after the requested time is rejected. Nested future CTB observations, bars, SEC publication/revision timestamps and split dates are removed. Missing metadata is not invented. Historical universe audit counts are kept, but complete original listings and excluded-stock fundamentals were not archived; current listings never replace past listings. Chinese classification is used only when already verified in historical inputs; names are never used to guess ownership or business geography.

The detector cannot accept future outcome arguments and cannot import the outcome reader. It freezes the entire candidate list and hashes the selection before the user can request later prices. The evaluator refuses a modified selection. TOP20 is the first20 of this frozen engine ranking, including failures and high-risk observations rather than selecting eventual winners.

## Outcome limitations

IEX daily bars do not prove executable quotes. The first subsequent trading-day aggregate opening price, plus configurable slippage, is a **proxy**, not the signal-time fill. Its session and exact fill time are unverified; an aggregate daily open is never labeled a verified09:30 ET open. Returns at1/3/5 observed sessions, maximum high/low excursions and10% target versus stop order are calculated only when price bases are comparable. At least20 overlapping daily OHLCV rows must agree across archive revisions; corporate actions within the outcome window invalidate comparison. This overlap check is used only by the outcome reader. It never rewrites historical detection inputs.

A daily candle touching both the target and stop has unknown order and is not counted as a success. Premarket/aftermarket fills, bid/ask spread, full-market volume, commissions, delisting losses and gap fills are not reconstructed. Price basis failure and immature horizons are explicit. Partial replays and price proxies never enter the verified success rate; initially that rate is null. Do not interpret null as0% or as a successful backtest.

Statuses: VERIFIED REPLAY requires all timing and universe inputs; PARTIAL REPLAY has usable but incomplete historical inputs; NOT REPRODUCIBLE has no admissible snapshot or required scope data. Current archives are deliberately PARTIAL because full historical listings, metadata and source publication records are incomplete.

## Independent operation

`python -m hunter.time_machine --snapshot public/time-machine/COMMIT.json --et 2026-10-22T16:00 --output /tmp/replay.json`

`Time Machine archive and verification` runs independently after successful squeeze scans or changes to its own files, and supports manual dispatch. It only writes `public/time-machine/`. Existing live engine files, weights, scan schedules, SEC collection and Telegram state are untouched. The Pages workflow also deploys after a successful independent archive run.

Tests cover future availability/event/retrieval times, nested future records, ET DST ambiguity, unsupported history, delisted historical symbols, unverified Chinese classification, selection tampering, target/stop ambiguity, price-basis and split checks. The workflow also executes the real browser Python path and records desktop/mobile screenshots.

## External reconstruction versus archive replay

`ARCHIVE REPLAY` remains the existing immutable Git-input replay. It does not
claim to rediscover a historical market. `HISTORICAL RECONSTRUCTION` is an
independent CLI / GitHub Actions path:

```
python -m hunter.time_machine_reconstruct --et 2026-10-15T12:00 --scope all
```

The workflow `time-machine-reconstruct.yml` uses the existing Alpaca Secrets.
The static web page cannot safely dispatch authenticated provider requests, so
its reconstruction mode links to **Run workflow**, copies the selected ET input,
and loads the completed report only if its ET cutoff and scope match exactly.
It does not silently return an archive result for a reconstruction request.

Discovery queries the provider's **active AND inactive** US equity catalogue,
without filtering on today's exchange, tradability, company name or market cap.
Every discovered symbol is queried for historical raw IEX daily bars, followed
by 5-minute bars for every symbol with completed historical daily prices. No
stored candidate rows or future-return lists are read. Pagination is exhaustive;
failed requests and missing prices are counted. Raw adjustment and `asof` set to
the selected ET date avoid today's split adjustment and default ticker mapping.
Historical corrections or incomplete mapping can still exist.

This catalogue is NOT a point-in-time security master. Historical listing,
common-share/ADS classification, small-cap eligibility, China classification,
missing delisted/renamed symbols, shares outstanding, SEC contracts, splits and
CTB are unverified. Price-existence instruments are analyzed with the unchanged
engine as **eligibility-unverified exploratory signals**, not verified small-cap
candidates. Unknown total historical population and unknown omitted count remain
`null`, never zero. Reports expose request, price, 22-bar usability, intraday,
access-error and eligibility counts. Original-published availability and data
vintage are unverified, therefore this source produces **PARTIAL REPLAY** (or
NOT REPRODUCIBLE if no usable prices), never VERIFIED REPLAY or a success rate.

`retrieved_at` is an audit clock, and may be today. Reconstruction envelopes must
provide `event_time <= available_at <= cutoff`, `available_at <= retrieved_at`,
a source and availability basis. If supplied, `published_at <= available_at`.
Archive replay keeps its strict historical capture-clock gate. Nested future
SEC acceptance, publication, observation and market timestamps are still
removed. Today's retrieval is not retroactively used as a borrow observation.
The adapter deliberately supplies **no historical borrow observations**.
Daily aggregates are excluded until next ET midnight +20min; intraday until bar
end +20min. These are conservative estimated availability boundaries, **not
proof of original publication time or of original unrevised values**. They are
explicitly unverified. Evaluation data is neither downloaded nor imported by
the reconstruction path. Existing archive outcomes are disabled for these
results because comparable split/vintage/entry basis has not been established.

Primary provider references checked for this implementation:
- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/reference/getassets
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://alpaca.markets/learn/fetch-historical-data
- https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
- https://beta.nasdaqtrader.com/Trader.aspx?id=DailyListPD

Free IEX history is partial-market data; a currently downloadable symbol
directory is not a historical listing master. Full historical exchange coverage
has not been demonstrated from these free endpoints. Permissions are measured
by actual workflow responses, not assumed from documentation.

Full fetched input and complete frozen selection evidence is uploaded as a gzip
GitHub Actions artifact (90-day retention). The public JSON contains coverage,
TOP20 and the full selection hash, avoiding oversized Git blobs.

SEC submissions and XBRL are freely accessible, but current company metadata
is not a historical symbol master. A filing- and issuer-linked publication
verification adapter is not implemented in this reconstruction. SEC facts are
therefore missing, not fabricated or labeled impossible to obtain. Reference:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Malformed-symbol HTTP400 batches are bisected to salvage valid symbols;
terminal failures list affected symbols and timeframe. Auth/entitlement errors
are not multiplied into per-symbol retries. Read-only reconstruction jobs are serialized without canceling an earlier user request, independently of live Hunter scheduling.

## Authenticated site execution and future portability

`TIME MACHINE 실행` creates a fresh UUID-correlated request through an
owner-private Sites gateway. The existing completed-report lookup remains
separate. Native Sites login may open once in a branded execution window;
no Actions UI, manual date copying, API key or GitHub token is in browser code.
Exact-origin/window/nonce messages return progress and TOP20 to the original page.
The server issues the job ID; workflow run ID and immutable result path are kept
per job. Submission is idempotent; ambiguous dispatch is not auto-replayed.

The gateway source, tests and schema are mirrored under `time-machine-service/`.
The operational Site is a deployment component of the current BREAKOUT HUNTER
work; no `gms0181-kr/breakout-time-machine` repository or migration is created.
Runtime configuration lives outside source. A future move must transfer the
existing single engine at a pinned commit/hash, not create a competing engine.
Collector adapters, request wrapper, gateway and UI use explicit inputs/outputs;
none reads or mutates Telegram state or imports the live scan entry point.

Deployment components:
- Python collection + existing engine: `hunter/time_machine_job.py`
- Workflow adapter: `.github/workflows/time-machine-reconstruct.yml`
- Auth, quota, job status: `time-machine-service/worker/index.js`
- Gateway source repository: provisioned by Sites, not a new user GitHub repo
- Public origin config: `public/time-machine-service.json` (contains URL only)
- Browser bridge: `public/time-machine-runner.js`

Required server credential: `GITHUB_ACTIONS_TOKEN`, a runtime **secret** with
Actions read/write for **only** `gms0181-kr/breakout-hunter`. It cannot be obtained
from GitHub Secrets or exported from the connected GitHub app. Missing credential
must return 503 and cannot count as an end-to-end execution success. Configure it
through secure server settings, never source code, browser bundles or chat.
Existing Alpaca Secrets remain solely in GitHub Actions.

Two-date collection verification is a distinct workflow from authenticated
button E2E verification. Fresh external API calls and completed report UI tests
do not prove an authenticated dispatch succeeded. Report these separately.

The gateway has no automatic paid-service purchase and does not change Site
sharing. It is owner-private; do not make it public without a new auth review.

Completed external reports are indexed during Pages publication by
`scripts/build_time_machine_job_index.py`. The lookup control matches ET time and
scope to an immutable report and explicitly labels reuse as **not a new
collection**. The execution button always issues a fresh authenticated request.
The index only verifies report metadata; it neither reruns scoring nor changes
PARTIAL replay into historical eligibility verification.
