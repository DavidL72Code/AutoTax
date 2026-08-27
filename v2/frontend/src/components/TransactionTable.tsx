"use client";

import { Fragment, useState } from "react";
import { useApp } from "@/components/AppState";
import { Badge, Button, inputClass } from "@/components/ui";
import { Transaction } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

const SOURCE_COPY: Record<string, string> = {
  domain: "sender domain",
  registry: "known vendor",
  regex: "pattern match",
  llm: "model",
  heuristic: "fallback",
};

const ISSUE_COPY: Record<string, string> = {
  vendor_missing: "No vendor could be identified",
  amount_missing: "No total found in the email",
  amount_not_positive: "Total is zero or negative",
  amount_implausible: "Total is implausibly large",
  tax_negative: "Tax is negative",
  tax_exceeds_plausible_share: "Tax is too large a share of the total",
  total_does_not_reconcile: "Subtotal plus tax does not equal the total",
  date_in_future: "Date is in the future",
  date_unparseable: "Date could not be read",
};

export function issueText(issue: string): string {
  return ISSUE_COPY[issue] ?? issue.replaceAll("_", " ");
}

function Trace({ row }: { row: Transaction }) {
  return (
    <div className="grid gap-5 bg-canvas px-4 py-4 md:grid-cols-2">
      <div>
        <h4 className="mb-2 text-[12px] font-medium text-ink">How this was parsed</h4>
        <ol className="space-y-1.5">
          {row.steps.map((step, index) => (
            <li key={`${step.node}-${index}`} className="flex gap-2 text-[12px]">
              <span className="w-[62px] shrink-0 font-mono text-ink-3">{step.node}</span>
              <span className="flex-1 text-ink-2">{step.detail}</span>
              <span className="num shrink-0 text-ink-3">{step.ms}ms</span>
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h4 className="mb-2 text-[12px] font-medium text-ink">Field sources</h4>
        <ul className="space-y-1.5">
          {Object.entries(row.sources).map(([field, source]) => (
            <li key={field} className="flex justify-between gap-2 text-[12px]">
              <span className="text-ink-2">{field}</span>
              <span className="text-ink-3">{SOURCE_COPY[source] ?? source}</span>
            </li>
          ))}
        </ul>
        {row.issues.length ? (
          <>
            <h4 className="mt-4 mb-2 text-[12px] font-medium text-ink">Open questions</h4>
            <ul className="space-y-1 text-[12px] text-warn">
              {row.issues.map((issue) => (
                <li key={issue}>{issueText(issue)}</li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </div>
  );
}

function EditRow({ row, onDone }: { row: Transaction; onDone: () => void }) {
  const { patch } = useApp();
  const [vendor, setVendor] = useState(row.vendor ?? "");
  const [amount, setAmount] = useState(row.amount?.toString() ?? "");
  const [tax, setTax] = useState(row.tax?.toString() ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await patch(row.id, {
        vendor: vendor.trim() || null,
        amount: amount === "" ? null : Number(amount),
        tax: tax === "" ? null : Number(tax),
      });
      onDone();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-2 bg-canvas px-4 py-3">
      <div className="w-48">
        <span className="mb-1 block text-[12px] text-ink-3">Vendor</span>
        <input className={`${inputClass} w-full`} value={vendor} onChange={(e) => setVendor(e.target.value)} />
      </div>
      <div className="w-28">
        <span className="mb-1 block text-[12px] text-ink-3">Amount</span>
        <input className={`${inputClass} num w-full`} value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" />
      </div>
      <div className="w-28">
        <span className="mb-1 block text-[12px] text-ink-3">Tax</span>
        <input className={`${inputClass} num w-full`} value={tax} onChange={(e) => setTax(e.target.value)} inputMode="decimal" />
      </div>
      <Button variant="primary" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </Button>
      <Button variant="quiet" onClick={onDone}>
        Cancel
      </Button>
    </div>
  );
}

export function TransactionTable({ rows }: { rows: Transaction[] }) {
  const { remove } = useApp();
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] border-collapse">
        <thead>
          <tr className="border-b border-line text-left text-[12px] text-ink-3">
            <th className="px-4 py-2 font-normal">Vendor</th>
            <th className="px-4 py-2 font-normal">Date</th>
            <th className="px-4 py-2 font-normal">Category</th>
            <th className="px-4 py-2 text-right font-normal">Tax</th>
            <th className="px-4 py-2 text-right font-normal">Amount</th>
            <th className="px-4 py-2 text-right font-normal">Confidence</th>
            <th className="w-[92px] px-4 py-2 font-normal" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const expanded = open === row.id;
            return (
              <Fragment key={row.id}>
                <tr
                  className="cursor-pointer border-b border-line align-middle hover:bg-canvas"
                  onClick={() => setOpen(expanded ? null : row.id)}
                >
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] text-ink">{row.vendor ?? "Unknown"}</span>
                      {row.status === "needs_review" ? <Badge tone="needs_review">review</Badge> : null}
                    </div>
                  </td>
                  <td className="num px-4 py-2 text-[13px] text-ink-2">{shortDate(row.date)}</td>
                  <td className="px-4 py-2 text-[13px] text-ink-2">{row.category ?? "—"}</td>
                  <td className="num px-4 py-2 text-right text-[13px] text-ink-2">{money(row.tax)}</td>
                  <td className="num px-4 py-2 text-right text-[13px] font-medium text-ink">{money(row.amount)}</td>
                  <td className="num px-4 py-2 text-right text-[13px] text-ink-3">
                    {Math.round((row.confidence ?? 0) * 100)}%
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
                      <Button
                        size="sm"
                        variant="quiet"
                        onClick={() => {
                          setEditing(editing === row.id ? null : row.id);
                          setOpen(row.id);
                        }}
                      >
                        Edit
                      </Button>
                      <Button size="sm" variant="quiet" onClick={() => remove(row.id)}>
                        Delete
                      </Button>
                    </span>
                  </td>
                </tr>
                {expanded ? (
                  <tr className="border-b border-line">
                    <td colSpan={7} className="p-0">
                      {editing === row.id ? (
                        <EditRow row={row} onDone={() => setEditing(null)} />
                      ) : (
                        <Trace row={row} />
                      )}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
