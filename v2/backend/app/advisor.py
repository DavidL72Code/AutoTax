"""The advisor: answers questions about spending, from the ledger only.

Ported from v1's `/api/advisor/chat`, with the same scope limits and the same
refusal to be mistaken for a licensed professional. Two things are different
here, both deliberate:

* It is built from the *aggregated* ledger, totals by month, by category, by
  merchant, never from records row by row and never from email text. v2 does
  not store email bodies at all, so there is nothing else it could see, but the
  summary is assembled explicitly so that stays true if that ever changes.
* The disclaimer is not left to the model. The prompt asks for it, but the UI
  renders it regardless, because a guardrail that depends on the model
  remembering is not a guardrail.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Optional

from . import llm

MAX_MESSAGE = 2000
MAX_HISTORY_TURNS = 8
MAX_TURN_CHARS = 800

# A merchant name is the one piece of attacker-influenced text that reaches this
# prompt: it was read out of an email nobody vetted. Nothing upstream bounds it,
# so bound it here. The model ignores instructions smuggled in a merchant name,
# which was tested, but an unbounded one still costs tokens and can crowd out
# the real figures.
MAX_VENDOR_CHARS = 60

# What it will talk about, and what it will hand back. Kept as data rather than
# buried in the prompt so the boundary is reviewable.
IN_SCOPE = (
    "Budgeting, cutting spending, and tracking habits",
    "Building an emergency fund",
    "Saving strategies in general terms (high-yield savings, CDs, I-bonds)",
    "Retirement account types (Roth IRA, Traditional IRA, 401k, 403b, SEP-IRA)",
    "Passive investing basics (index funds, ETFs, asset allocation)",
    "Debt payoff strategies (avalanche, snowball, consolidation)",
    "Housing basics (rent vs buy, down payment planning, mortgage concepts)",
    "General personal finance education",
)

OUT_OF_SCOPE = (
    "Specific securities to buy or sell, options, or crypto speculation",
    "Tax filing positions or legal advice",
    "Medical or insurance decisions",
    "Anything unrelated to personal finance",
    "Technical questions about ReceiptAuto itself",
)


def _parse(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _short(name: str) -> str:
    """One line, bounded. A merchant name spanning several lines would read as
    structure in a prompt that is parsed by layout."""
    flat = " ".join(str(name).split())
    return flat[:MAX_VENDOR_CHARS] if len(flat) <= MAX_VENDOR_CHARS else flat[:MAX_VENDOR_CHARS] + "..."


def spend_summary(rows: list[dict[str, Any]], today: Optional[date] = None) -> str:
    """Aggregates only. No vendor-level line items, no dates of individual
    purchases, no ids, the shapes of the spending, not the receipts."""
    today = today or datetime.now(timezone.utc).date()
    # Not `> 0`: a refund is negative, and dropping it would report the spend it
    # cancelled as though it stood. Zero and missing amounts are still excluded,
    # since they carry no information about spending either way.
    usable = [r for r in rows if float(r.get("amount") or 0) != 0]
    if not usable:
        return "The ledger is empty. No receipts have been parsed yet."

    total = 0.0
    by_category: dict[str, float] = defaultdict(float)
    by_vendor: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)

    for row in usable:
        amount = float(row.get("amount") or 0)
        total += amount
        by_category[row.get("category") or "Uncategorised"] += amount
        by_vendor[row.get("vendor") or "Unknown"] += amount
        when = _parse(row.get("date"))
        if when:
            by_month[when.strftime("%Y-%m")] += amount

    months = sorted(by_month)
    this_month = by_month.get(today.strftime("%Y-%m"), 0.0)
    average = total / max(len(months), 1)

    lines = [
        f"Receipts on file: {len(usable)}",
        f"Total recorded: ${total:,.2f} across {len(months)} month(s)",
        f"This month so far: ${this_month:,.2f}",
        f"Average month: ${average:,.2f}",
        "",
        "By category:",
    ]
    for name, value in sorted(by_category.items(), key=lambda kv: -kv[1]):
        # A share of the total is only meaningful when there is a total. Refunds
        # can net it to zero, and a percentage of nothing is a crash.
        share = f" ({value / total * 100:.0f}%)" if total else ""
        lines.append(f"  {name}: ${value:,.2f}{share}")

    lines.append("")
    lines.append("Largest merchants:")
    for name, value in sorted(by_vendor.items(), key=lambda kv: -kv[1])[:8]:
        lines.append(f"  {_short(name)}: ${value:,.2f}")

    if len(months) > 1:
        lines.append("")
        lines.append("Recent months:")
        for month in months[-6:]:
            lines.append(f"  {month}: ${by_month[month]:,.2f}")

    return "\n".join(lines)


def build_prompt(message: str, history: list[dict[str, Any]], summary: str) -> str:
    turns = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "").strip()[:MAX_TURN_CHARS]
        if not content:
            continue
        if role == "user":
            turns.append(f"User: {content}")
        elif role == "assistant":
            turns.append(f"Advisor: {content}")

    return "\n".join([
        'You are "RA Advisor", a personal finance helper inside ReceiptAuto.',
        "You are NOT a licensed financial advisor, accountant or tax professional, and you",
        "must never imply otherwise. For anything that turns on someone's full circumstances,",
        "say plainly that a qualified professional is the right person to ask.",
        "",
        "The reader's spending, aggregated from their own receipts:",
        summary,
        "",
        "ANSWER QUESTIONS ABOUT:",
        *(f"- {item}" for item in IN_SCOPE),
        "",
        "DECLINE, BRIEFLY AND WITHOUT LECTURING:",
        *(f"- {item}" for item in OUT_OF_SCOPE),
        "",
        "PRIVACY: the figures above are aggregates. Speak in terms of categories, months and",
        "proportions. Never invent a transaction, a date or a merchant that is not listed.",
        "If the ledger does not support a claim, say so rather than estimating.",
        "",
        "STYLE: concise, practical, warm. Bullet points for anything actionable.",
        "Under 250 words. Use - for bullets and *word* for emphasis; no headers, no **.",
        "Never use an em dash. Use a comma, a colon or a full stop instead.",
        "",
        *turns,
        f"User: {message}",
        "Advisor:",
    ])


def _strip_speaker(reply: str) -> str:
    """The prompt ends with `Advisor:` to cue the turn, and the model sometimes
    answers by repeating it. Harmless to the meaning, but it reads as a leaked
    prompt to anyone who sees it."""
    text = reply.strip()
    for label in ("Advisor:", "RA Advisor:", "Assistant:"):
        if text.startswith(label):
            text = text[len(label) :].lstrip()
    return text


async def answer(message: str, history: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    reply = await llm.ask(build_prompt(message, history, spend_summary(rows)), max_tokens=600)
    return _strip_speaker(reply)
