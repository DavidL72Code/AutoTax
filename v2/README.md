# Receipts v2

A rebuild of the receipt pipeline as a LangGraph state machine, with a new
Next.js front end, Firestore storage, and outputs an accountant can use. v1 is
still in the repo root and still runs; nothing here touches it.

- **[docs/pipeline.md](docs/pipeline.md)**, the graph, which nodes call the
  model, and what flows through the state
- **[docs/evals.md](docs/evals.md)**, quality, latency, robustness, injection
  resistance and security, with thresholds
- **[Security](#security)** below, the threat model, what is stored, and what
  the 21 automated checks assert

## What changed and why

**v1 was one function with an AI escape hatch.** `parser_select` chose a
parser, the parser ran regexes, and anything the regexes missed went to Gemini.
When a number came out wrong there was no way to ask *which* step believed
what.

**v2 is eight nodes and two loops**, each node answering one question and
recording its answer.

```
triage ──not a receipt──────────────────────────────────────────────► end
   │
extract ──► resolve ──complete?──► enrich ──► validate ──clean──► persist
               │                     ▲            │                  │
               └──gaps──► escalate ──┘            │                  ▼
                              ▲                   │              Firestore
                              └───fixable, ≤2─────┤                  +
                                                  │            learned rules
                                            unresolved               │
                                                  ▼                  │
                                          await_review  ── interrupt()
                                                  │      Command(resume=…)
                                                  └──────► back to validate
```

| Node | Question | Cost |
|---|---|---|
| `triage` | Is this a purchase at all? | rules; model only when ambiguous |
| `extract` | What do the patterns prove? | free |
| `resolve` | Who was paid? | free |
| `escalate` | What could the rules not prove? | one batched model call |
| `enrich` | What kind of spending is this? | free for known merchants |
| `validate` | Does the arithmetic hold? | free |
| `await_review` | What does a person say? | free, the thread pauses here |
| `persist` | Is this worth saving unattended? | free |

Three things fall out of that shape:

- **Every record carries its own trace.** The UI shows the steps that produced
  each row and which source each field came from, memory, sender domain,
  pattern match, model, or a person. A wrong number is debuggable.
- **`validate` can send work back.** A total that does not reconcile against
  its own subtotal and tax goes back to `escalate` with just the suspect
  fields, at most twice.
- **Two things send a receipt to a person.** A blocking defect is one. The
  other is confidence: it is field coverage weighted by where each value came
  from, so a domain match counts for more than a model guess, and under 0.55
  the record is held back even when its sums agree.
- **The queue *is* the paused computation.** When the automatic options run
  out, `await_review` calls `interrupt()`: LangGraph checkpoints the thread and
  the run ends. Answering resumes that thread, and the human's numbers go
  through `validate` like everyone else's before anything is written.

### Memory

Two kinds, deliberately separate (`app/graph/persistence.py`):

- **Checkpointer**, per thread (`{user_id}:{email_id}`), short-term. Every
  superstep, which is what makes `interrupt`/resume possible. In-process by
  default; set `CHECKPOINT_BACKEND=sqlite` to survive restarts.
- **Store**, cross-thread, long-term. What corrections taught the system:
  sender domain → vendor, vendor → category. `resolve` and `enrich` read it
  first on every later email, so the same correction is never asked for twice
  and the review queue drains instead of refilling.

### Batching without batch code

`app/llm.py` coalesces concurrent requests of the same kind into a single
prompt. Nodes call `await llm.EXTRACT.submit(...)` as if it were one request;
whatever else is in flight in the same ~120ms window rides along. v1 got the
same saving by hand-writing a separate batch path that duplicated the
single-email logic. Here, one code path, batching underneath.

## Benchmark

Sixteen layouts, generated with known ground truth. A receipt's subtotal is the
sum of its own line items and its total is built from that subtotal, so the
arithmetic holds by construction and a layout that breaks it has to say so.
Each layout declares the path it should take and the issues it should raise, so
the harness scores routing, not only values.

```bash
cd backend
./.venv/bin/python tests/evals/run.py                    # everything
./.venv/bin/python tests/evals/run.py --only quality     # accuracy and routing
./.venv/bin/python tests/evals/run.py --no-llm           # rules only, free, instant
./.venv/bin/python tests/evals/run.py --layout table_dot_leader   # one layout
```

41 receipts, model available:

| tier | receipts | values correct | threshold |
|---|---|---|---|
| `rules_only` | 21 | 100% | 100% |
| `escalate` | 11 | 100% | 75% |
| `review` | 8 | 100% | 60% |
| `skipped` | 1 | 100% | 100% |

Routing 100%, coverage 16/16 layouts, 32 auto-saved, 8 flagged, 1.26s per
receipt. Thresholds differ by tier because a layout the rules should settle has
no excuse, and one written to defeat them does.

**46 model asks became 9 HTTP requests.** Four layouts finish with none at all:
`table_dot_leader`, `flattened_html_cells`, `receipt_header_block` and
`forwarded_thread`, 15 of the 41 receipts, resolved entirely by patterns.

Scoring per layout rather than as one average is the point. A regression
localises to the layout that caused it instead of moving an aggregate by two
points, and a layout that stops being sampled fails the run rather than
disappearing quietly.

Two limits the corpus measures rather than hides. `_MONEY` requires two decimal
places, so `1.234,56 EUR` and a zero-decimal yen amount always escalate and are
then recorded as USD, reported as `non_usd_recorded_as_usd` instead of failed.
And `validate` reconciles subtotal plus tax against the total without modelling
shipping, discounts or tips, so `shipping_and_discount` asserts that drift as
its *expected* issue and the gap stays visible.

## What the data is for

Parsing receipts is the boring half. These are the outputs (`app/insights/`,
surfaced on **Statement** and **Insights**):

**Recurring-charge detection.** A subscription is a *pattern*, not a category:
same merchant, steady interval, steady amount. Detected from the ledger rather
than tagged by hand, with cadence, annualised cost, next expected charge, and
price changes. Personally that answers "what am I committed to each year?"; on
the business side it is evergreen-vendor tracking.

A price rise compares the latest charge against the median of the ones before
it, so what it reports is "this *just* went up", not a history. That is worth
stating because the demo fixture got it wrong from the start: it planted the rise
in the middle of the series, where the new price is already the median, and so
reported a change of 0.0% no matter how large the rise. Fixed by counting the
risen charges back from the most recent one.

**Anomalies worth acting on.** Duplicate billing (same merchant, same amount,
days apart), subscription price rises with the annual delta in dollars, lapsed
recurring charges, charges far outside a merchant's normal range, and missing
tax where a merchant normally charges it, usually a parsing miss, which means
understated recoverable tax.

**Monthly statement.** Total against the prior month, per-category deltas, top
movers, largest single charge, spend per day, and a month-end projection while
the month is still running (never after it closes, a finished month is a fact,
not a forecast).

**Tax and apportionment.** Sales tax paid by month and category, effective
rate, and a business apportionment driven by an editable category → chart-of-
accounts map (`app/insights/accounts.py`). Default mappings to edit with your
bookkeeper, explicitly not tax advice.

**Three exports**, all carrying the source Gmail message id so any row traces
back to the email:

| Shape | For | Contents |
|---|---|---|
| `ledger` | a person | date, vendor, category, gross, tax, net, payment method, status, confidence |
| `journal` | accounting software | double entry, expense debited, tax split to its own line, payment source credited |
| `expenses` | whoever signs off | account code, business share, claimable amount |

Untrusted text (a vendor name is whatever the email said) is neutralised before
it reaches a spreadsheet cell.

## Running it

Backend:

```bash
cd v2/backend
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./run.sh                      # http://localhost:8020
```

Front end:

```bash
cd v2/frontend
npm install && npm run dev    # http://localhost:3000
```

Check every dependency before wiring up Gmail:

```bash
cd v2/backend
./.venv/bin/python tests/check_setup.py --port 8020
```

It reports Firestore, Gemini, the Fernet key and the OAuth redirect URI, with
the fix for whatever is wrong, and prints no secret values.

### Configuration

Read from the repo-root `.env`, so an existing v1 setup works as-is.

| Variable | Used for |
|---|---|
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | the escalation calls (optional, rules run without it) |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | connecting Gmail |
| `FERNET_KEY` | encrypting the stored refresh token |
| `FIREBASE_PROJECT_ID` + service account | Firestore; otherwise a JSON file under `backend/data/` |
| `LLM_MIN_INTERVAL_SECONDS`, `LLM_RPM_LIMIT` | pacing, sized for a free-tier key by default |

Set `NEXT_PUBLIC_API_BASE` in `frontend/.env.local` if the API is not on
`http://localhost:8020`.

### Firebase

Firestore was never actually reachable in this repo before v2. The service
account JSON in `.env` is pretty-printed, and dotenv stops at the first
newline, so the value that reached the app was the single character `{`, and
both versions silently fell back to local storage. `app/store/firestore_client.py`
now reads the brace-balanced block straight out of `.env` (case-insensitively,
because the Firebase console writes the key as `..._json`), so nobody has to
re-flatten a key.

Collections:

| Collection | Contents |
|---|---|
| `transactions` | shared with v1. v2 adds `status`, `confidence`, `issues`, `sources`, `steps`; v1 ignores keys it does not know, so both versions can run against the same data |
| `receipts_v2_accounts` | one document per connected Gmail address, refresh token encrypted |
| `receipts_v2_sessions` | session tokens with a 30-day expiry |
| `receipts_v2_demo` | sample-inbox runs, kept away from real ledgers |

When you connect a Gmail address, v2 looks for v1 user documents with the same
address and reads that ledger too, so existing history is visible rather than
looking empty.

### Gmail

Read-only (`gmail.readonly`). The refresh token is encrypted with your Fernet
key before it is written, and disconnecting deletes it. Email bodies are never
stored, only extracted fields, the parse trace, and the Gmail message id,
which is what stops the next sync re-parsing the same receipt.

One thing needs doing in the Google Cloud console by hand: the OAuth client's
authorised redirect URI must match the port the API is actually serving. It is
currently registered for `http://localhost:8000/api/google/callback` while v2
defaults to `8020`. Either add
`http://localhost:8020/api/google/callback` to the client and point
`GOOGLE_OAUTH_REDIRECT_URI` at it, or run the API on 8000.
`tests/check_setup.py` will tell you which way it currently disagrees.

## Security

**The premise: email bodies are attacker controlled.** Anyone can send you a
message, and that message is fed to a language model and rendered in a browser.
Every control below either keeps untrusted text away from something privileged,
or keeps something privileged out of a place untrusted text reaches.

```bash
cd v2/backend
./.venv/bin/python tests/evals/run.py --only security
```

21 checks, run against the real ASGI app with no network. The full table is in
[docs/evals.md](docs/evals.md#security).

### Where untrusted text goes, and what meets it

| Path | Control |
|---|---|
| email body → model prompt | a financial excerpt, not the whole message; `validate` then does arithmetic the model cannot argue with |
| email body → vendor identity | the sender domain outranks anything in the body, so body text cannot rename a merchant |
| email body → spreadsheet | a leading `=`, `+`, `-` or `@` in any cell is neutralised before export |
| email body → browser | rendered as text, never as markup; no `dangerouslySetInnerHTML` anywhere |
| merchant name → advisor prompt | collapsed to one line and bounded, since nothing upstream bounds it |

The model ignoring an instruction smuggled into a merchant name was tested
directly, and it does. The bound exists because an unbounded name still costs
tokens and crowds out the real figures.

### What is stored

Email bodies are not. The ledger keeps extracted fields, the parse trace, and
the Gmail message id, which is what stops the next sync re-parsing the same
receipt. Gmail access is read-only (`gmail.readonly`). The refresh token is
Fernet-encrypted before it is written and deleted on disconnect. Session tokens
are 256-bit random, stored server side with a 30-day expiry, in an HttpOnly
`SameSite=Lax` cookie.

The advisor is built from **aggregates**, totals by month, category and
merchant, never from records row by row. No order numbers, payment methods,
message ids or individual dates reach its prompt. It is assembled explicitly
that way so it stays true if v2 ever does store more.

### Tenancy

Every data route refuses an anonymous caller. Reads are scoped to the caller's
ids; writes check ownership before touching a record. Both are asserted with
two live accounts rather than argued from the code, because `PATCH` and
`DELETE /api/transactions/{id}` once had no ownership check at all and returned
another account's record happily.

### Rate limits

`app/ratelimit.py`. Two kinds, because they answer different questions: `allow`
is per caller, and `budget` is global, since a per-caller limit does nothing
against many callers and the model quota is one shared pool.

| Endpoint | Per caller | Global |
|---|---|---|
| `POST /demo` | 3 runs / 10 min **per address** | 600 receipts / hour |
| `POST /sync` | 6 starts / 5 min per user | none |
| `POST /advisor/chat` | 12 / min per user | 240 / min |
| `POST /review/{id}` | 60 / min per user | none |
| `GET /google/auth-url` | 10 / 5 min per address | none |

The sample run is keyed by address, not user, because it mints a fresh identity
every time and a per-user limit would count to one forever. Its global budget
counts **receipts rather than runs**, or a caller picking their own `limit`
spends ten times the quota against the same single unit. The address comes from
`x-forwarded-for`, since the API sits behind a proxy; treat it as best effort,
it raises the cost of replaying the sample run, it does not make it impossible.

This is not a substitute for a limiter at the edge. It lives in one process, so
a second instance doubles every allowance, and it forgets everything on restart.
What it does do is stop the two failure modes that have actually happened here.

Per-run work is bounded too: `max_results` is capped at 500, the sample run at
25, and 16 emails are in the graph at once (`runner.run_many`). The in-memory
tables that used to grow without limit, sync runs, OAuth states and sample
inboxes, are all bounded now.

### Found and fixed

**OAuth login CSRF.** The `state` was only held server side, which proves a flow
started *here*, not that it started in *this browser*. An attacker could begin a
flow, hand the victim the callback URL, and land the victim's browser on a
session for the attacker's Google account. The state is now also a short-lived
HttpOnly cookie, compared with `compare_digest`.

**An unbounded OAuth state table.** Swept only when someone called
`/google/auth-url`, which is unauthenticated, so it was not a bound at all.

**A published API schema.** `/api/docs` and the OpenAPI JSON enumerated every
route, parameter and shape in production. Development only now.

**Tenant isolation on write.** See *Tenancy* above.

**A security check measuring the wrong thing.** `security.py` asserted prompt
length against body length, so adding to the prompt failed a check about how
much of the *email* was being sent. It now measures the share of body lines that
reach the model. Written up in [docs/fixtures.md](docs/fixtures.md).

### Not claimed

No edge rate limiting, no WAF, no audit log, no key rotation, no penetration
test. `/api/health` makes a live model call, so it is a readiness report for a
person rather than something to poll. The sample inbox holds generated fixtures
in process for the life of a demo session; they are text the server wrote
itself, they never touch Firestore, and they are dropped when the session ends.

## Deploying

Two services, one origin as far as a browser is concerned.

**The API** runs on Render from `v2/backend/Dockerfile`. Pure Python: it neither
builds nor serves the interface, so there is no Node in the image. Set the
Dockerfile path and the build context together, both relative to the service's
root directory, or they compound: a root of `v2/backend` with a context of
`./v2/backend` resolves to `v2/backend/v2/backend`.

Every setting it reads is already present on the v1 service under the same name,
`FERNET_KEY` and the three `GOOGLE_OAUTH_*` values included, and both versions
serve the OAuth callback at `/api/google/callback`, so Google Cloud Console
needs nothing. `DATABASE_URL` and the `FIREBASE_WEB_*` keys go unread: v2 uses
Firestore alone.

**The interface** runs on Vercel with the root directory set to `v2/frontend`
and nothing else. `vercel.json` forwards `/api` to the Render host at Vercel's
routing layer, which runs before the static files are served, so it works with
`output: "export"` where Next's own rewrites do not exist. That address is
written into the file because `vercel.json` interpolates no environment
variables, and the file takes no comments: Vercel rejects unknown keys.

Because the browser only ever sees Vercel's origin, the session cookie is not
cross-site and `samesite=lax` keeps working, and the API needs no CORS entry.

**Or one service.** Building the front end and letting FastAPI serve the export
alongside `/api` also works, and is simpler still: one host, one deploy. The
route handler is already there and skips itself when no export is present.

## Layout

```
backend/
  app/
    graph/          state, node implementations, wiring, patterns, vendor registry
    demo_data/      the sample corpus: receipts.py (the data model),
                    layouts.py (16 renderers plus what each one proves),
                    corpus.py (assembly, recurring charges, planted duplicates,
                    and the trim that keeps a demo run inside the quota)
    insights/       recurring charges, anomalies, statements, tax, exports
    ingest/gmail.py Gmail fetch and body flattening
    store/          Firestore client, transaction repository, account store
    advisor.py      spending questions, answered from the aggregated ledger
    llm.py          Gemini access, request coalescing, rate gate
    ratelimit.py    per-caller and global ceilings on what costs money
    notifications.py findings turned into a feed
    sync.py         run tracking and the SSE progress stream
    diagnostics.py  readiness checks for every external dependency
    api/routes.py   HTTP surface
  tests/
    eval_graph.py   the lighter accuracy benchmark
    check_setup.py  readiness report
    evals/          quality, latency, robustness, injection, security
frontend/
  src/app/          home, dashboard, transactions, statement, insights,
                    advisor, review, notifications, settings
  src/components/   shell, top bar, landing, graph diagram, charts, table,
                    theme provider, shared primitives
  src/lib/i18n/     every string the app can show, one file per locale
  scripts/          translate.mjs, generates a locale file from en.json
docs/               pipeline diagram, eval documentation, fixture rewrite notes
```

## Interface

**Localised.** Every string the site shows lives in `src/lib/i18n`, keyed the
same way in each locale, so "what is untranslated?" is a diff rather than a hunt
through the UI. That includes the parse traces: nodes emit a key and its values
beside the English sentence, and `triage` returns a reason code rather than
prose, so a trace reads in the reader's language and stays countable. `Intl`
handles dates, currency and plural forms. `scripts/translate.mjs` drafts a new
locale from `en.json` and rejects any translation that dropped a placeholder;
the output is committed so a speaker can correct it in a diff.

**Two themes.** Light is not the dark theme lightened. The dark one earns depth
from a lit top edge and a deep shadow on near-black, and neither survives on
paper, so light drops both and uses a warm ground with hairline rules instead.
Same geometry, same type, same accents, different material.

**The advisor** answers questions about spending from the aggregated ledger,
totals by month, category and merchant. It never receives a record row by row
and never an email body. The prompt states it is not a licensed financial
advisor and lists what it declines; the page renders that disclaimer too,
because a guardrail that depends on the model remembering is not a guardrail.

**The sample inbox writes nothing.** Demo sessions route to an in-process
backend, so a visitor trying the app never touches Firestore, and the data dies
with the session. Signing in with Google replaces a demo session rather than
requiring a sign-out first.

**Fifteen receipts, not ninety-eight.** A sample run costs real model calls, and
six months of generated history unabridged is 98 receipts, about thirty of which
escalate. A handful of demo visits was enough to exhaust a day of a free-tier
quota and leave every later run stalling on 429s. What survives the trim is
chosen rather than sampled: the duplicate pair and one subscription series are
kept whole, because half a series is not a price rise and one of two identical
charges is not a duplicate, and the rest of the budget goes to layouts that have
not appeared yet. Measured end to end at 15 receipts, 16s, 15 model calls, one
paused for review. The cost is layout coverage, 12 of 14 rather than all of
them: a run this short cannot both show every layout and carry a history.

## Front end

The dark theme is **ported from v1's `styles.css`, not reinvented**, same
`#060a14` base, same panel treatment (gradient fill, `inset 0 1px 0` top
highlight, `0 20px 60px` shadow, 20px radius, lit hairline across the top
edge), same 44px buttons with the blue gradient and inset highlight, same 52px
inputs with the 4px focus ring, same 18/24px table padding and uppercase
letter-spaced headers, same Inter / IBM Plex Mono / Space Grotesk trio. What
changed is the information architecture, not the look.

Those treatments are tokenised rather than hardcoded, which is what lets a
light theme exist without imitating them. See **Interface** above.

**Brand.** The mark is a square with a triangular notch struck into each side, one closed path, four-fold symmetric, flat, no gradient. It depicts nothing.
That is deliberate: the reference points are Porsche, YSL and Chase, none of
which draw the thing the company sells, and none of which have any depth or
gradient in them. Chase's octagon is one shape rotated four times; this is the
same logic in positive space, which is what keeps it legible at favicon size.

Set in caps with open tracking, because architectural type suits a geometric
mark better than friendly mixed case.

Two accents do two jobs, and keeping them apart is what lets a heritage mark
sit above a working UI: **brass `#c6a15b` is the brand** (mark, wordmark,
identity), **blue `#3b82f6` is the interface** (primary button, focus rings,
links, chart bars). Colour is a single value in `public/brand/mark.svg` if you
want the mark in blue or white instead.

`public/brand/mark.svg` is the live logo, `app/icon.svg` the favicon, and
`components/Brand.tsx` the mark, wordmark and lockup. Earlier explorations are
kept alongside as `mark-*.svg`.

**Five destinations, each doing one job:**

| | |
|---|---|
| **Dashboard** | The front door and the working screen. The graph is drawn as a graph, with live traffic on it: each node shows how many receipts passed through and its average time, the last node to run pulses, and the retry and human loops are drawn in. Beside it, the per-email trace; underneath, the ledger summary. |
| **Review** | Receipts the graph paused on because they would not reconcile. Answering one resumes the thread from where it stopped. |
| **Transactions** | The full ledger. Search, filter, export. A row opens to show which step decided each field. |
| **Statement** | One month closed out: change against last month, tax paid, and the three exports. |
| **Insights** | What only shows up across months, subscriptions, price rises, duplicate charges, concentration. |

"Overview" and "Activity" used to be separate pages describing the same run
from two angles, and the one that actually did something was filed under
*System*. They are one dashboard now.

**Navigation is the rail; the bar is utility.** The sidebar carries the brand,
the sync action (with a live progress bar during a run), and navigation. The slim bar above it
carries only the two things that follow you around every page: the notification
bell and the account. Neither duplicates the other, and there are no tabs. On
small screens the same rail slides in as a drawer. Filtering lives in a toolbar
above the grid it filters, so it never competes with navigation for a click.

Signing in *is* connecting Gmail, one Google grant, no second account to
create, so the top-right control is a plain **Sign in with Google** button
until you have one, and your account chip afterwards.

**Notifications** live behind the bell, with a dropdown of the six most recent
and a full page at `/notifications`. They are derived, not stored, recomputed
from the ledger on every request, so they cannot go stale or contradict the
data. Duplicate charges,
subscription price rises with the annual delta, lapsed recurring charges,
outliers, missing tax, receipts waiting on a human, and bills landing in the
next four days. Ids are stable hashes of what the notification is *about*, so
the same finding keeps its id across runs and stays read once you have read it;
only the read-marks are persisted, and they are pruned when the underlying
finding disappears.

Charts use a single hue, identity is carried by axis labels, so there is no
categorical palette to misread and no legend to decode, and each has a table
view for screen readers and for copying numbers out.

The **Activity** page streams a live run: every email, every node, every
decision, as it happens.
