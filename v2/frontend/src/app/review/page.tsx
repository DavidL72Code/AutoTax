"use client";

import { useState } from "react";
import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { issueText } from "@/components/TransactionTable";
import { Button, Card, Empty, inputClass } from "@/components/ui";
import { Transaction } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

function ReviewCard({ row }: { row: Transaction }) {
  const { patch, remove } = useApp();
  const [vendor, setVendor] = useState(row.vendor ?? "");
  const [amount, setAmount] = useState(row.amount?.toString() ?? "");
  const [tax, setTax] = useState(row.tax?.toString() ?? "");
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-3">
      <div className="grid gap-5 px-4 py-4 md:grid-cols-[1fr_260px]">
        <div>
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-[14px] font-medium text-ink">{row.vendor ?? "Unidentified vendor"}</h3>
            <span className="num text-[12px] text-ink-3">{shortDate(row.date)}</span>
          </div>

          <ul className="mt-2 space-y-1">
            {row.issues.map((issue) => (
              <li key={issue} className="text-[13px] text-warn">
                {issueText(issue)}
              </li>
            ))}
          </ul>

          <div className="mt-3 border-t border-line pt-3">
            <p className="mb-1.5 text-[12px] text-ink-3">What the pipeline did</p>
            <ol className="space-y-1">
              {row.steps.map((step, index) => (
                <li key={`${step.node}-${index}`} className="flex gap-2 text-[12px]">
                  <span className="w-[62px] shrink-0 font-mono text-ink-3">{step.node}</span>
                  <span className="text-ink-2">{step.detail}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="space-y-2.5">
          <div>
            <span className="mb-1 block text-[12px] text-ink-3">Vendor</span>
            <input className={`${inputClass} w-full`} value={vendor} onChange={(e) => setVendor(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="mb-1 block text-[12px] text-ink-3">Amount</span>
              <input className={`${inputClass} num w-full`} value={amount} inputMode="decimal" onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div>
              <span className="mb-1 block text-[12px] text-ink-3">Tax</span>
              <input className={`${inputClass} num w-full`} value={tax} inputMode="decimal" onChange={(e) => setTax(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <Button
              variant="primary"
              disabled={busy}
              onClick={() =>
                run(() =>
                  patch(row.id, {
                    vendor: vendor.trim() || null,
                    amount: amount === "" ? null : Number(amount),
                    tax: tax === "" ? null : Number(tax),
                  }),
                )
              }
            >
              Confirm
            </Button>
            <Button variant="quiet" disabled={busy} onClick={() => run(() => remove(row.id))}>
              Discard
            </Button>
          </div>
          <p className="text-[12px] text-ink-3">
            Parsed total {money(row.amount)} · confidence {Math.round((row.confidence ?? 0) * 100)}%
          </p>
        </div>
      </div>
    </Card>
  );
}

export default function ReviewPage() {
  const { transactions, loading } = useApp();
  const rows = transactions.filter((row) => row.status === "needs_review");

  return (
    <>
      <PageHeader
        title="Review"
        description="Receipts the pipeline could not close out on its own. Confirming one marks it settled."
      />
      {loading ? (
        <Card>
          <Empty title="Loading…" />
        </Card>
      ) : rows.length ? (
        rows.map((row) => <ReviewCard key={row.id} row={row} />)
      ) : (
        <Card>
          <Empty title="Nothing to review">
            Every parsed receipt reconciled — a vendor, a positive total, and tax that adds up.
          </Empty>
        </Card>
      )}
    </>
  );
}
