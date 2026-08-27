# Receipts v2

A rebuild of the receipt pipeline as a LangGraph state machine, with a new
Next.js front end. v1 is still in the repo root and still runs; nothing here
touches it.

## What changed and why

**v1 was one function with an AI escape hatch.** `parser_select` chose a parser,
the parser ran regexes, and anything the regexes missed went to Gemini. When a
number came out wrong there was no way to ask *which* step believed what.

**v2 is seven nodes, each answering one question and recording its answer.**

```
triage ──not a receipt──────────────────────────────────────► end
   │
extract ──► resolve ──complete?──► enrich ──► validate ──clean──► persist
               │                     ▲            │
               └──gaps──► escalate ──┘            └──fixable──► escalate
                                                      (once)
```

| Node | Question | Cost |
|---|---|---|
| `triage` | Is this a purchase at all? | rules; model only when ambiguous |
| `extract` | What do the patterns prove? | free |
| `resolve` | Who was paid? | free |
| `escalate` | What could the rules not prove? | one batched model call |
| `enrich` | What kind of spending is this? | free for known merchants |
| `validate` | Does the arithmetic hold? | free |
| `persist` | Save, or flag for a human? | free |

Two things fall out of that shape:

- **Every record carries its own trace.** The UI shows the steps that produced
  each row and which source each field came from — sender domain, pattern
  match, or model. A wrong number is now debuggable.
- **`validate` can send work back.** A total that does not reconcile against
  its subtotal and tax goes back to `escalate` once with just the suspect
  fields, then to the review queue rather than into your ledger.

## Batching without batch code

`app/llm.py` coalesces concurrent requests of the same kind into a single
prompt. Nodes call `await llm.EXTRACT.submit(...)` as if it were one request;
whatever else is in flight in the same ~120ms window rides along. v1 got the
same saving by hand-writing a separate batch path that duplicated the
single-email logic. Here, one code path, batching underneath.

## Benchmark

Ten generated receipts with known ground truth — five clean layouts, five messy
ones with decoy dollar values and indirect labels. Generated locally and
deterministically, so runs are comparable.

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

## Running it

Backend:

```bash
cd v2/backend
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./run.sh                      # http://localhost:8010
```

Front end:

```bash
cd v2/frontend
npm install && npm run dev    # http://localhost:3000
```

Configuration is read from the repo-root `.env`, so an existing v1 setup works
as-is. The only values v2 needs:

| Variable | Used for |
|---|---|
| `GOOGLE_API_KEY`, `GEMINI_MODEL` | the escalation calls (optional — rules run without it) |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | connecting Gmail |
| `FERNET_KEY` | encrypting the stored refresh token |
| `FIREBASE_PROJECT_ID` + service account | optional; otherwise a JSON file under `backend/data/` |

Set `NEXT_PUBLIC_API_BASE` in `frontend/.env.local` if the API is not on
`http://localhost:8010`.

## Layout

```
backend/
  app/
    graph/          state, node implementations, wiring, patterns, vendor registry
    ingest/gmail.py Gmail fetch and body flattening
    store/          JSON store by default, Firestore when configured
    llm.py          Gemini access, request coalescing, rate gate
    sync.py         run tracking and the SSE progress stream
    api/routes.py   HTTP surface
  tests/            benchmark and fixtures
frontend/
  src/app/          overview, transactions, review, activity, settings
  src/components/   shell, charts, table, shared primitives
```

## Front end

Light, dense, and deliberately plain: one accent colour reserved for data marks
and the primary action, hairline rules instead of shadows, tabular numerals so
columns line up. Charts use a single hue — identity is carried by axis labels,
so there is no categorical palette to misread and no legend to decode. Each
chart has a table view for screen readers and for copying numbers out.

The **Activity** page streams a live run: every email, every node, every
decision, as it happens.
