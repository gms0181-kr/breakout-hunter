# BREAKOUT HUNTER Time Machine execution gateway

This owner-private Sites Worker submits the existing repository's historical
reconstruction workflow. It has no stock-selection/scoring engine and no Alpaca
credentials. Existing Alpaca Secrets remain exclusively in GitHub Actions.

Deployment requires `GITHUB_ACTIONS_TOKEN` as a Sites runtime **secret**, scoped
only to `gms0181-kr/breakout-hunter`, Actions read/write (dispatch + status).
The current GitHub connector does not export its credentials or expose workflow
dispatch, so deployment alone cannot establish that permission. Missing secret
returns 503 before creating a job; it never reports that collection started.

Sites native owner-private sign-in is the security boundary. Do not change its
audience to public. `OWNER_PRIVATE_CONFIRMED=true` is set only after native
get_site confirms owner-only access. Browser visitors get normal native identity;
platform service access without a native owner user ID cannot submit or read jobs. The owner
email may be configured as an additional check, never as a replacement for the
platform access policy. Origin checks, atomic global concurrency/hour/day quotas,
UUID idempotency, per-principal job lookups and private/no-store responses apply.

The GitHub Pages click opens this branded authenticated runner window for the
native sign-in boundary. It sends status/results back using an exact-origin,
exact-window and nonce checked postMessage channel. No API keys or GitHub tokens
are sent to the browser. Popup blocking and sign-in errors are surfaced; no
manual Actions UI or date-copy workflow is required.

Dispatch is made once. A network ambiguity becomes dispatch_unknown and resolves
by UUID-correlated workflow title; it is never automatically re-dispatched.
Status refresh has an atomic 10-second poll lease. Completed result JSON must
match job UUID, ET time, scope, as_of and unchanged scoring-engine SHA256.
Request results use immutable per-UUID paths, never reconstruction-latest.json.
No cross-date cache is used. A repeated idempotency key resumes the same job and
is explicitly marked resumed; a new click uses a fresh key.

The access and token configuration still needs live verification before any
site-button end-to-end completion claim. Mock dispatch tests are not live API
execution evidence. No new paid service has been purchased by this project.
