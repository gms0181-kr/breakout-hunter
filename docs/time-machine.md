# TIME MACHINE — independent point-in-time research

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
