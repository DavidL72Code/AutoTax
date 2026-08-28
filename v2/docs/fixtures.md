# Fixture rewrite

**Status: built.** `app/demo_data/` is the package described below.
What the corpus then found in the pipeline is in [Findings](#findings-what-the-new-corpus-caught).

The quality corpus could not support the numbers the eval harness reported from
it. This is what was wrong, what replaced it, and the three pipeline defects the
replacement immediately caught.

## What is wrong now, measured

`history_cases(6)` produces 99 receipts from **five** body layouts:

| source | layouts | receipts |
|---|---|---|
| `_build_organized_body` — `random.choice` of four templates | 4 | 48 |
| `_build_messy_body` — one f-string | 1 | 51 |

All 99 share one subject template (`"Your receipt from {vendor}"`) across 11
senders. Every receipt that takes the `escalate` path — 51 of 99, and every
escalation observed in any run — comes from that single messy f-string.

Three consequences:

1. **Accuracy percentages are near-meaningless.** "38 records scored 1.00" is
   one layout answered ~19 times, not 38 independent observations. The same
   applies to `section_quality`'s vendor/amount/tax percentages in
   `tests/evals/run.py`.
2. **`validate` is untestable.** `_build_messy_body` draws item prices from
   `random.uniform(2.5, 45.0)` independently of the subtotal it was passed, so
   line items sum to nothing related to the total. There is no layout whose
   arithmetic is *coherent*, so `total_does_not_reconcile`, the `retry ×2` loop
   and the `await_review` branch never fire. Every run reports
   `0 paused · 0 flagged`.
3. **The cross-line extraction path has no coverage.** `patterns.extract_amount`
   has a documented fallback for HTML receipts that split a label and its value
   across table cells, so the two land on different lines. Every existing layout
   puts `Label: $value` on one line, so that fallback is never exercised.

Note what is *not* wrong: `ROBUSTNESS` and `INJECTION` in `tests/evals/cases.py`
are 15 hand-written, structurally distinct cases with per-case expectations.
That is the model to follow. The gap is confined to the generated quality
corpus.

## Design

### A receipt whose arithmetic holds

One dataclass as the single source of truth, with the invariant asserted at
construction:

```python
@dataclass(frozen=True)
class Receipt:
    vendor: str
    domain: str
    date: date
    items: tuple[LineItem, ...]      # (description, qty, unit_price)
    tax_rate: float
    shipping: float = 0.0
    discount: float = 0.0
    tip: float = 0.0
    currency: str = "USD"

    @property
    def subtotal(self): return round(sum(i.qty * i.unit_price for i in self.items), 2)
    @property
    def tax(self):      return round(self.subtotal * self.tax_rate, 2)
    @property
    def total(self):    return round(self.subtotal + self.tax + self.shipping - self.discount + self.tip, 2)
```

`subtotal` derived from the items is the change that makes `validate`
meaningful. A layout that deliberately breaks the arithmetic then has to do so
explicitly, via `corrupt_total`, and declare the issue it should produce.

### Layouts as a registry

Each layout is a pure renderer plus the metadata the harness needs to assert
routing, not just values:

```python
@dataclass(frozen=True)
class Layout:
    name: str
    render: Callable[[Receipt], str]
    weight: float                      # sampling share
    expected_path: Path                # RULES_ONLY | ESCALATE | REVIEW
    expected_issues: tuple[str, ...] = ()
    tests: str = ""                    # one line: what this layout is here to prove
```

`demo_cases` / `history_cases` sample by declared weight and then append any
layout the draw missed, so a layout can never silently drop out of the corpus.
`section_quality` fails if any layout is uncovered.

### Model HTML as *flattened* text, not markup

`ingest/gmail.py::_body` prefers `text/plain`, and when only HTML exists it runs
it through BeautifulSoup and collapses whitespace before the graph ever sees it.
So a fixture containing raw `<table>` markup would test something the graph
never receives. The HTML layouts must be written as the **post-flattening
output**: tags gone, whitespace collapsed, and — the part that matters — table
cells become separate lines, so a label and its value are no longer adjacent.

## The layouts

Sixteen, against the five they replace. Generated from the registry in
`app/demo_data/layouts.py`, which is the only place these are declared.

| layout | expected path | what it proves | expected issues |
|---|---|---|---|
| `eur_comma_decimal` | escalate | 1.234,56 EUR — period and comma inverted | — |
| `flattened_html_inline` | escalate | one amount split across symbol / dollars / cents lines | — |
| `installments` | escalate | order value vs the amount actually charged today | — |
| `jpy_no_decimals` | escalate | zero-decimal currency | — |
| `no_explicit_total` | escalate | no total stated anywhere; must be summed from line items | — |
| `processor_relay` | escalate | vendor is in the body; the sender domain is a processor | — |
| `reconciliation_block` | escalate | decoys: auth hold, pending charge, prior balance | — |
| `mismatched_total` | review | subtotal + tax != total; the only path to the retry loop | `total_does_not_reconcile` |
| `shipping_and_discount` | review | legitimate total with shipping and a discount; validate cannot model either | `total_does_not_reconcile` |
| `zero_total` | review | a zero total is valid data but must not be banked silently | `amount_not_positive` |
| `flattened_html_cells` | rules_only | every label separated from its value by a newline | — |
| `forwarded_thread` | rules_only | quoted stale receipt below the live one | — |
| `plain_labeled` | rules_only | baseline: labelled total on one line | — |
| `receipt_header_block` | rules_only | blank-line separated blocks, 'Amount Charged' phrasing | — |
| `table_dot_leader` | rules_only | dot leaders and column alignment around the value | — |
| `image_only` | skipped | nothing to extract; must not invent a number | — |

Four of them — `mismatched_total`, `shipping_and_discount`, `zero_total`,
`image_only` — exercise branches that had no coverage at all.

## Harness changes

- `section_quality` reports **per layout**, not one aggregate. A regression then
  localizes to a layout instead of moving a single percentage.
- Assert `expected_path` and `expected_issues` per case, so routing is under
  test, not only extracted values.
- Thresholds per difficulty tier rather than one global number: rules-only
  layouts should be 100% and cost zero model calls; escalation layouts get a
  lower bar.
- `--layout NAME` to run one.

## Migration

`app/demo_data/` keeps the `demo_emails()` / `history_emails()` / `demo_cases()`
/ `to_graph_email()` signatures the single module had, so `/api/demo` needed no
changes at all. `tests/evals/cases.py` and `tests/fixtures.py` changed only to
carry the new per-case metadata through, and to tolerate a `None` amount where a
document states none. `history_cases` keeps planting the recurring charges, the price rise and
the duplicate billing that the Insights page is built to find — it just draws
bodies from the registry instead of the two builders.

## Consequences to expect

- **Eval runs get slower and cost more.** More layouts defeat the regex by
  design, so escalation rate rises.
- **The dashboard will look different.** `needs_review` stops being 0. The
  review queue and the `await_review` interrupt finally get exercised in the
  demo — which is the point, but it changes what the sample inbox demonstrates.
- **Reported accuracy will probably drop.** That is a more honest number, not a
  regression.

Non-goal: real captured emails. Privacy, and they cannot ship in the repo.




## Findings: what the new corpus caught

Five defects, none of them in the fixture. All fixed.

### Dot leaders defeated every label pattern

`table_dot_leader` scored 0% on values. `patterns._labelled_value` matched
`Label: $value` and `Label   $value`, but not

```
Subtotal ................... $47.25
```

because the dots sit between the label and the number where the pattern wanted
whitespace. Dot leaders are one of the most common receipt styles, so every
such receipt was quietly escalating to the model — correct output, paid for with
an API call that should not have happened. The fix is one alternative in the
pattern list: `[\s.·]+` in place of `\s+`. That layout now scores 100% with
zero model calls.

### `persist` kept a second, smaller copy of the blocking set

`graph.BLOCKING` listed four issues including `total_does_not_reconcile`;
`persist` had its own literal set of three, without it. In interactive mode the
`await_review` branch caught the difference, so nothing was visibly wrong. In
non-interactive mode — which is *every eval run* — a receipt whose own
arithmetic contradicted itself was saved as `parsed`. The eval could never have
seen this, because the corpus had no receipt whose arithmetic was coherent
enough for the check to mean anything.

`BLOCKING` now lives in `state.py` and both call sites read it.

### `financial_snippet` could halve an amount before the model saw it

`flattened_html_inline` renders one amount as four lines — `$`, `387`, `.`, `97`
— which is what a styled `<span>` layout becomes after HTML flattening. The
model returned `97.00`. It was right to: `financial_snippet` keeps lines
matching a financial keyword plus one line of context, and the bare `387` and
`.` lines matched nothing, so the text handed to the model read `Total / $ / 97`.
A $387.97 charge would have been banked as $97.

This is the worst of the five, because it is silent and it corrupts a value
rather than dropping one. `patterns.glue_split_amounts` now rejoins a run of
fragment lines when — and only when — the joined result reads as a single
amount, so a stacked price column in a table stays two prices. `financial_snippet`
runs it first.

### The prompt-hygiene security check measured the wrong thing

`security.py` asserted `len(all_prompts) < len(body) * 6` against a 77-character
body. The intent is "an excerpt of the email travels, not the whole email", but
the quantity measured includes our own static instructions — so lengthening the
instructions failed a *security* check without any more of the email being sent.
It now measures what share of the body's own lines reach the model (≤40%), and
asserts the full body is never present, against a body long enough for the
property to be testable.

### Two layouts were declared harder than they are

Written on assumption, corrected by measurement:

- `flattened_html_cells` — assumed to need the model. `extract_amount`'s
  cross-line fallback reads it correctly, so it is `RULES_ONLY`. The fallback
  had no coverage before; now it has some.
- `forwarded_thread` — assumed to need the model to pick the live receipt over
  the quoted stale one. `_labelled_value` scans top-down and the live total is
  above, so the rules get it. `RULES_ONLY`.

And one that turned out to take a fourth path entirely: `image_only` is rejected
by `triage`, which is right — an email with no purchase record in it is not a
receipt. That needed a `Path.SKIPPED` the design did not have.

## Known limitations, now measured rather than assumed

- **`_MONEY` requires two decimal places.** `¥15,737` and `1.234,56 EUR` cannot
  match it at all, so both non-USD layouts always escalate. The model reads them
  fine, but the currency is dropped: `draft.currency` defaults to `"USD"` and
  nothing sets it. Reported as `non_usd_recorded_as_usd` rather than failed.
- **The demo inbox and the eval corpus deliberately differ.** `jpy_no_decimals`
  is `eval_only`: a ¥15,737 receipt recorded as $15,737 is exactly what the eval
  should measure, and it put $59,126 on the dashboard when it reached the demo.
  The demo inbox draws from the other fifteen.
- **`validate` does not model shipping, discounts or tips.** It reconciles
  `subtotal + tax` against the total, so any receipt carrying an adjustment
  drifts. `shipping_and_discount` asserts that drift as the *expected* issue, so
  the gap stays visible instead of looking like a parser error.
