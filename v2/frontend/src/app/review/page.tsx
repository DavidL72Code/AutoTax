"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { useIssueText } from "@/components/TransactionTable";
import { Button, Empty, Field, GmailLink, Panel, Pill, StepScore, inputClass } from "@/components/ui";
import { ReviewQueue, ReviewSource, Transaction, api, blockedOnModel } from "@/lib/api";
import { useT, useTrace } from "@/lib/i18n";
import { money, shortDate } from "@/lib/format";

type Item = Transaction & { live: boolean; source?: ReviewSource | null };

function ReviewItem({ row, onDone, gmailConnected }: { row: Item; onDone: (message: string) => void; gmailConnected: boolean }) {
  const { t } = useT();
  const trace = useTrace();
  const issueText = useIssueText();
  const [vendor, setVendor] = useState(row.vendor ?? "");
  const [amount, setAmount] = useState(row.amount?.toString() ?? "");
  const [tax, setTax] = useState(row.tax?.toString() ?? "");
  const [subtotal, setSubtotal] = useState(row.subtotal?.toString() ?? "");
  const [category, setCategory] = useState(row.category ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (action: "confirm" | "discard") => {
    if (!row.email_id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.resolveReview(row.email_id, {
        action,
        ...(action === "confirm"
          ? {
              vendor: vendor.trim() || null,
              amount: amount === "" ? null : Number(amount),
              tax: tax === "" ? null : Number(tax),
              subtotal: subtotal === "" ? null : Number(subtotal),
              category: category.trim() || null,
            }
          : {}),
      });
      onDone(
        result.resumed
          ? `Resumed the paused thread — re-validated and saved as ${result.record?.status}.`
          : `Checkpoint had expired, so the answer was applied directly (saved as ${result.record?.status}).`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="mb-4" flush>
      <div className="grid md:grid-cols-[1fr_340px]">
        <div className="border-b border-[var(--hairline)] px-6 py-6 md:border-r md:border-b-0">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="font-[family-name:var(--font-display)] text-[1.05rem] font-bold text-ink">
                {row.vendor ?? "Unidentified vendor"}
              </span>
              {blockedOnModel(row) ? (
                <Pill tone="neutral">{t("review.blockedBadge")}</Pill>
              ) : row.live ? (
                <Pill tone="accent">{t("review.threadPaused")}</Pill>
              ) : (
                <Pill tone="neutral">{t("review.checkpointExpired")}</Pill>
              )}
            </div>
            <span className="num text-[0.85rem] text-ink-4">{shortDate(row.date)}</span>
          </div>

          {blockedOnModel(row) ? (
            <p className="mt-4 rounded-[10px] border border-[var(--hairline-strong)] bg-[var(--wash)] px-4 py-3 text-[0.85rem] leading-relaxed text-ink-3">
              {t("review.blockedNote")}
            </p>
          ) : null}

          {/* The complaint is about three numbers, so show the sum rather than
              only naming it. Without this the reviewer cannot tell which of the
              three is the misread one. */}
          {row.issues.includes("total_does_not_reconcile") &&
          row.subtotal != null &&
          row.tax != null &&
          row.amount != null ? (
            <p className="num mt-4 text-[0.85rem] text-amber">
              {t("review.arithmetic", {
                subtotal: money(row.subtotal),
                tax: money(row.tax),
                sum: money(Number((row.subtotal + row.tax).toFixed(2))),
                amount: money(row.amount),
              })}
            </p>
          ) : null}

          <ul className="mt-4 space-y-1.5">
            {row.issues.map((issue) => (
              <li key={issue} className="text-[0.9rem] text-amber">
                {issueText(issue)}
              </li>
            ))}
          </ul>

          {/* Enough to find the message in your own mailbox, which is where the
              authoritative copy lives and the only place its contents are read.
              `email_id` is the Gmail message id, so it deep-links straight to
              it. The body is never sent here. */}
          {row.source ? (
            <div className="mt-5 rounded-[10px] border border-[var(--hairline-strong)] px-4 py-3">
              <div className="eyebrow mb-2">{t("review.emailFrom")}</div>
              <div className="space-y-0.5 text-[0.85rem]">
                <div className="text-ink-2">{row.source.subject ?? t("review.noSubject")}</div>
                <div className="num text-[0.8rem] text-ink-4">
                  {row.source.sender} · {shortDate(row.date)}
                </div>
              </div>
              <div className="mt-2">
                <GmailLink emailId={row.email_id} connected={gmailConnected} />
              </div>
            </div>
          ) : (
            <div className="mt-5 text-[0.82rem] text-ink-4">
              {t("review.expiredNote")}
            </div>
          )}

          <div className="eyebrow mt-6 mb-3">{t("review.whereStopped")}</div>
          <ol className="space-y-2">
            {row.steps.map((step, index) => (
              <li key={`${step.node}-${index}`} className="flex gap-3 text-[0.85rem]">
                <span className="num w-[92px] shrink-0 text-ink-4">{step.node}</span>
                <span className="flex-1 text-ink-2">{trace(step)}</span>
                <StepScore value={step.confidence} />
              </li>
            ))}
          </ol>
        </div>

        <div className="px-6 py-6">
          <div className="space-y-4">
            <Field label={t("review.vendor")}>
              <input className={inputClass} value={vendor} onChange={(e) => setVendor(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("review.amount")}>
                <input className={`${inputClass} num`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </Field>
              <Field label={t("review.tax")}>
                <input className={`${inputClass} num`} inputMode="decimal" value={tax} onChange={(e) => setTax(e.target.value)} />
              </Field>
            </div>
            {/* `validate` reconciles subtotal + tax against the total, so all
                three have to be visible and all three correctable — otherwise a
                misread subtotal can only be cleared by falsifying the others. */}
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("review.subtotal")}>
                <input className={`${inputClass} num`} inputMode="decimal" value={subtotal} onChange={(e) => setSubtotal(e.target.value)} />
              </Field>
            </div>
            <Field label={t("review.category")}>
              <input className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)} />
            </Field>
          </div>

          <div className="mt-5 flex gap-3">
            <Button variant="primary" disabled={busy} onClick={() => send("confirm")}>
              {busy ? "Sending…" : "Confirm"}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => send("discard")}>
              Discard
            </Button>
          </div>

          <p className="mt-4 text-[0.8rem] leading-relaxed text-ink-4">
            Your values re-enter the graph at <span className="num">await_review</span> and pass back through{" "}
            <span className="num">validate</span> before anything is written — the same arithmetic the model had
            to satisfy. A vendor you set is remembered for this sender.
          </p>
          {error ? <p className="mt-3 text-[0.85rem] text-down">{error}</p> : null}
        </div>
      </div>
    </Panel>
  );
}

export default function ReviewPage() {
  const { refresh, session } = useApp();
  const { t } = useT();
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setQueue(await api.reviewQueue());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the queue");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const done = async (message: string) => {
    setNotice(message);
    await load();
    await refresh();
  };

  if (error) {
    return (
      <Panel flush>
        <Empty title="Nothing to review">{error}</Empty>
      </Panel>
    );
  }
  if (!queue) return <p className="text-[0.9rem] text-ink-3">{t("common.loading")}</p>;

  const live = queue.items.filter((item) => item.live).length;
  // Two different asks hide behind one count: a receipt nobody can settle
  // without reading it, and one that only stalled because the model was down.
  const blocked = (queue?.items ?? []).filter((row) => blockedOnModel(row)).length;
  const learned = queue.learned.vendors.length + queue.learned.categories.length;

  return (
    <>
      <PageHeader
        title={t("review.title")}
        description={t("review.description")}
      />

      <div className="panel panel-sm mb-4 flex flex-wrap items-center gap-x-10 gap-y-2 px-6 py-4">
        <span className="text-[0.85rem] text-ink-4">
          {t("review.checkpointer")} <span className="num ml-1.5 text-ink-2">{queue.checkpointer}</span>
        </span>
        <span className="text-[0.85rem] text-ink-4">
          {t("review.pausedThreads")} <span className="num ml-1.5 text-ink-2">{live}</span> of {queue.items.length}
        </span>
        <span className="text-[0.85rem] text-ink-4">
          {t("review.learnedRules")} <span className="num ml-1.5 text-ink-2">{learned}</span>
        </span>
        {blocked ? (
          <span className="text-[0.9rem] text-ink-3">
            {t("review.splitBoth", { blocked, human: (queue?.items.length ?? 0) - blocked })}
          </span>
        ) : null}
        <span className="hidden">
        </span>
      </div>

      {notice ? (
        <div className="panel panel-sm mb-4 px-6 py-4 text-[0.9rem] text-ink-2">{notice}</div>
      ) : null}

      {queue.items.length ? (
        queue.items.map((row) => <ReviewItem key={row.id} row={row as Item} onDone={done} gmailConnected={Boolean(session?.gmail_connected)} />)
      ) : (
        <Panel flush>
          <Empty title="Queue is empty">
            Every receipt reconciled on its own — a vendor, a positive total, and tax that adds up.
          </Empty>
        </Panel>
      )}

      {learned ? (
        <Panel title="Learned from your corrections" flush className="mt-4">
          <div className="grid md:grid-cols-2">
            <ul className="space-y-2 border-b border-[var(--hairline)] px-6 py-5 md:border-r md:border-b-0">
              {queue.learned.vendors.map((entry) => (
                <li key={entry.domain} className="flex justify-between gap-4 text-[0.85rem]">
                  <span className="num text-ink-4">{entry.domain}</span>
                  <span className="text-ink-2">{entry.vendor}</span>
                </li>
              ))}
              {!queue.learned.vendors.length ? <li className="text-[0.85rem] text-ink-4">No sender rules yet</li> : null}
            </ul>
            <ul className="space-y-2 px-6 py-5">
              {queue.learned.categories.map((entry) => (
                <li key={entry.vendor} className="flex justify-between gap-4 text-[0.85rem]">
                  <span className="text-ink-4">{entry.vendor}</span>
                  <span className="text-ink-2">{entry.category}</span>
                </li>
              ))}
              {!queue.learned.categories.length ? <li className="text-[0.85rem] text-ink-4">No category rules yet</li> : null}
            </ul>
          </div>
          <p className="border-t border-[var(--hairline)] px-6 py-4 text-[0.8rem] text-ink-4">
            These live in the graph&apos;s cross-thread store. <span className="num">resolve</span> and{" "}
            <span className="num">enrich</span> read them on every later email, so the same correction is never
            asked for twice.
          </p>
        </Panel>
      ) : null}
    </>
  );
}
