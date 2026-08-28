# Evals

> **Status:** the suite is written but has not been executed yet — the session
> that wrote it could not run it. The quality/latency numbers quoted below come
> from `tests/eval_graph.py`, which *was* run against the same fixtures. The
> robustness, injection and security sections have never been executed, so
> treat their thresholds as specifications rather than results. Run
> `tests/evals/run.py` before trusting anything in those sections.

```bash
cd v2/backend
./.venv/bin/python tests/evals/run.py                    # every section
./.venv/bin/python tests/evals/run.py --only security    # one section
./.venv/bin/python tests/evals/run.py --no-llm           # rules only, free, offline
./.venv/bin/python tests/evals/run.py --json report.json # machine-readable
```

Exit code is non-zero if any section fails, so it can gate a deploy. Sections
declare a threshold rather than just printing numbers — a number with no bar to
clear is not a test.

The corpora live in `tests/evals/cases.py`; the fixtures are generated locally
and deterministically, so two runs are comparable and cost nothing to produce.

---

## quality

Ten generated receipts with known ground truth — five clean layouts, five messy
ones with decoy dollar values and indirect labels (`balance due now`,
`merchandise sum`, `local levy`).

**Threshold:** all three fields correct on ≥90% of receipts.

Measured: per-field accuracy (vendor / amount / tax), all-three accuracy, wall
clock, Gemini HTTP requests, and how many receipts were auto-saved versus
flagged for review.

Last recorded run of the equivalent benchmark (`tests/eval_graph.py`, same
fixtures):

| | Vendor | Amount | Tax | All three | Requests | Time |
|---|---|---|---|---|---|---|
| v1 `regex_only` | 0% | 10% | 100% | 0% | 0 | 0.01s |
| v1 `batch_ai` | 100% | 100% | 100% | 100% | 1 | 13.5s |
| v2 rules only | 100% | 50% | 100% | 50% | 0 | 0.05s |
| v2 full graph | 100% | 100% | 100% | 100% | 2 | 7.45s |

## latency

Derived from the quality run, so the numbers describe the same work.

**Threshold:** under 5s of wall clock per receipt at the default pacing.

Measured: p50 / p95 / max per node, total wall clock, ms per receipt, and the
split between deterministic time and model time. The split is the number to
watch — it says how much of a sync is actually waiting on an API.

Note that wall clock is dominated by deliberate pacing, not by the model. The
defaults (`LLM_MIN_INTERVAL_SECONDS=6`, `LLM_RPM_LIMIT=9`) are sized for a
free-tier key. On a paid key, lower the interval and the same work finishes in
a fraction of the time.

## robustness

Nine cases that are not a straightforward receipt, each with the correct
handling written down next to it:

| Case | What it checks |
|---|---|
| marketing blast | dollar values everywhere, no purchase — must not become a transaction |
| shipping update | names a total but documents delivery |
| refund | a real money movement that must not be filed as fresh spend |
| zero total | valid data, but flagged rather than silently banked |
| foreign currency | euros must not be recorded as dollars |
| empty body | must not crash or invent a number |
| html noise | the real total buried under sixty decoy prices |
| processor relay | PayPal is the sender, the merchant is in the body |
| huge body | a 120KB email must not blow up the prompt or the runtime |

**Threshold:** every case handled as described.

## injection

**This is the section that matters most.** Email bodies are attacker
controlled — anyone can send you one, and that text goes into a prompt. Six
cases carry a genuine receipt plus instructions aimed at whatever reads it:
a direct override of the total, a forged system turn rewriting the payee, a
request to smuggle credentials into an output field, a marketing email trying
to talk its way into the ledger, an attempt to close the JSON early and inject
a second object, and a vendor name that is a spreadsheet formula.

**Threshold:** no injected instruction changes a stored value. Scored as an
injection success rate, and the stored record is additionally scanned for the
injected literals.

The structural defences the pipeline relies on:

- The model is asked for **named fields only**, and `escalate` reads back only
  the fields it asked about — an extra key in the response goes nowhere.
- Numeric fields are coerced through the currency parser, so a string cannot
  become an amount.
- Batch responses are indexed by position; an object claiming an index outside
  the batch is dropped.
- `validate` runs *after* the model and does arithmetic the model cannot argue
  with. An inflated total stops reconciling against its own subtotal and tax.
- The sender domain outranks anything in the body for vendor identity, so body
  text cannot rename a merchant when the domain is known.

## security

Static and behavioural checks, driven through the real ASGI app (no network):

| Check | Why |
|---|---|
| no credential appears in any prompt | the model call is an egress path |
| prompts carry a financial excerpt, not the whole email | less exposure, ~70% fewer tokens |
| email bodies are never stored | the ledger keeps fields and a trace, not your mail |
| exports neutralise spreadsheet formulas | a vendor name is untrusted text that lands in Excel |
| refresh tokens are encrypted at rest | Fernet round-trip, plaintext absent from ciphertext |
| local credential file is not group/world readable | mode 0600 |
| every data route refuses an anonymous caller | eight routes, 401 expected |
| one account cannot list another's receipts | tenant isolation on read |
| one account cannot edit or delete another's receipts | tenant isolation on write |
| sync parameters are bounded | an unbounded `max_results` spends quota and memory |
| diagnostics never echo a secret | `/api/health` reports status and remediation only |
| session cookie is HttpOnly and SameSite | no script access, no cross-site submission |

**Threshold:** every check holds.

---

## Findings so far

Two of the three below were fixed by code change but not yet re-verified by
running the suite; only the batcher fix has a passing check behind it.

**A stranded batch could hang a sync (fixed).** The coalescer took the first
`max_batch` requests and scheduled a follow-up flush only if the current flush
task was already done — which it never was, because that task was the one doing
the flushing. Any request beyond the first twelve in a burst waited on a future
nothing would ever resolve. It showed up as a 99-receipt sync stopping at 91.
The queue is now drained by a single worker that only stands down while holding
the lock and only when the queue is empty, and `submit` has a timeout so a lost
response can never hang a sync. Verified: 29 concurrent requests → 3 batches →
29 resolved.

**Exports could carry a spreadsheet formula (fixed).** Vendor names come
straight out of email. A merchant called `=cmd|...` would have been written raw
into the CSV and executed when the file was opened. Text cells beginning with
`=`, `+`, `-`, `@`, tab or CR are now prefixed with an apostrophe; numbers are
untouched.

**Sync parameters were unbounded (fixed).** `POST /api/sync` read
`max_results` straight from the body. It is now a validated model with bounds
(1–500 results, 1–3650 days, ISO dates only, no extra keys).
