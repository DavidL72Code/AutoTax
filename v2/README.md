# Receipts v2

A rebuild of the receipt pipeline as a LangGraph state machine, with a new
Next.js front end, Firestore storage, and outputs an accountant can use. v1 is
still in the repo root and still runs; nothing here touches it.

- **[docs/pipeline.md](docs/pipeline.md)**, the graph, which nodes call the
  model, and what flows through the state
- **[docs/evals.md](docs/evals.md)**, quality, latency, robustness, injection
  resistance and security, with thresholds

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
| `persist` | Save, and keep what was learned | free |

Three things fall out of that shape:

- **Every record carries its own trace.** The UI shows the steps that produced
  each row and which source each field came from, memory, sender domain,
  pattern match, model, or a person. A wrong number is debuggable.
- **`validate` can send work back.** A total that does not reconcile against
  its own subtotal and tax goes back to `escalate` with just the suspect
  fields, at most twice.
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

Ten generated receipts with known ground truth, five clean layouts, five messy
ones with decoy dollar values and indirect labels.

```bash
cd backend
./.venv/bin/python tests/eval_graph.py            # full graph
./.venv/bin/python tests/eval_graph.py --no-llm   # rules only, free, instant
```

| | Vendor | Amount | Tax | All three | API requests | Time |
|---|---|---|---|---|---|---|
| v1 `regex_only` | 0% | 10% | 100% | 0% | 0 | 0.01s |
| v1 `individual_ai` | 100% | 100% | 100% | 100% | 10 | 168.3s |
| v1 `batch_ai` | 100% | 100% | 100% | 100% | 1 | 13.5s |
| **v2 rules only** | **100%** | 50% | 100% | 50% | **0** | **0.05s** |
| **v2 graph** | **100%** | **100%** | **100%** | **100%** | **2** | **7.45s** |

The rules-only row is the interesting one: v2 identifies every vendor with no
API call at all, because sender-domain resolution moved ahead of the model
instead of behind it. The five receipts it can't finish are flagged, not
guessed at.

## What the data is for

Parsing receipts is the boring half. These are the outputs (`app/insights/`,
surfaced on **Statement** and **Insights**):

**Recurring-charge detection.** A subscription is a *pattern*, not a category:
same merchant, steady interval, steady amount. Detected from the ledger rather
than tagged by hand, with cadence, annualised cost, next expected charge, and
price changes against the earlier baseline. Personally that answers "what am I
committed to each year?"; on the business side it is evergreen-vendor tracking.

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

## Layout

```
backend/
  app/
    graph/          state, node implementations, wiring, patterns, vendor registry
    insights/       recurring charges, anomalies, statements, tax, exports
    ingest/gmail.py Gmail fetch and body flattening
    store/          Firestore client, transaction repository, account store
    llm.py          Gemini access, request coalescing, rate gate
    sync.py         run tracking and the SSE progress stream
    diagnostics.py  readiness checks for every external dependency
    api/routes.py   HTTP surface
  tests/
    eval_graph.py   the accuracy benchmark
    check_setup.py  readiness report
    evals/          quality, latency, robustness, injection, security
frontend/
  src/app/          overview, transactions, statement, insights, review, activity, settings
  src/components/   shell, charts, table, shared primitives
docs/               pipeline diagram and eval documentation
```

## Front end

The visual language is **ported from v1's `styles.css`, not reinvented**, same
`#060a14` base, same panel treatment (gradient fill, `inset 0 1px 0` top
highlight, `0 20px 60px` shadow, 20px radius, lit hairline across the top
edge), same 44px buttons with the blue gradient and inset highlight, same 52px
inputs with the 4px focus ring, same 18/24px table padding and uppercase
letter-spaced headers, same Inter / IBM Plex Mono / Space Grotesk trio. What
changed is the information architecture, not the look.

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
