"use client";

import { Fragment, useState } from "react";
import { useApp } from "@/components/AppState";
import { useT, useTrace } from "@/lib/i18n";
import { Button, Field, GmailLink, Pill, StepScore, Th, inputClass } from "@/components/ui";
import { Transaction } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

/* Issue codes and field sources are translated from their code, so a new code
   surfaces as the raw code rather than as silently missing text. */
export function useIssueText() {
  const { t } = useT();
  return (issue: string) => {
    const text = t(`issue.${issue}`);
    return text === `issue.${issue}` ? issue.replaceAll("_", " ") : text;
  };
}

export function useCategoryText() {
  const { t } = useT();
  return (category: string | null | undefined) => {
    if (!category) return "—";
    const text = t(`category.${category}`);
    return text === `category.${category}` ? category : text;
  };
}

export function useSourceText() {
  const { t } = useT();
  return (source: string) => {
    const text = t(`source.${source}`);
    return text === `source.${source}` ? source : text;
  };
}

export function Trace({ row }: { row: Transaction }) {
  const { session } = useApp();
  const { t } = useT();
  const trace = useTrace();
  const issueText = useIssueText();
  const sourceText = useSourceText();
  return (
    <div className="grid gap-8 bg-[var(--wash)] px-6 py-6 md:grid-cols-[1.5fr_1fr]">
      <div>
        <div className="eyebrow mb-3">{t("transactions.howParsed")}</div>
        <ol className="space-y-2">
          {row.steps.map((step, index) => (
            <li key={`${step.node}-${index}`} className="flex gap-3 text-[0.85rem]">
              <span className="num w-[92px] shrink-0 text-ink-4">{step.node}</span>
              <span className="flex-1 text-ink-2">{trace(step)}</span>
              <StepScore value={step.confidence} />
              <span className="num shrink-0 text-ink-4">{step.ms}ms</span>
            </li>
          ))}
        </ol>
      </div>
      <div>
        <div className="eyebrow mb-3">{t("transactions.fieldSources")}</div>
        <ul className="space-y-2">
          {Object.entries(row.sources).map(([field, source]) => (
            <li key={field} className="flex justify-between gap-3 text-[0.85rem]">
              <span className="text-ink-2">{field}</span>
              <span className="text-ink-4">{sourceText(source)}</span>
            </li>
          ))}
        </ul>
        {session?.gmail_connected && row.email_id ? (
          <div className="mt-6">
            <div className="eyebrow mb-2">{t("transactions.theOriginal")}</div>
            <GmailLink emailId={row.email_id} connected />
          </div>
        ) : null}
        {row.issues.length ? (
          <>
            <div className="eyebrow mt-6 mb-3">{t("transactions.openQuestions")}</div>
            <ul className="space-y-1.5">
              {row.issues.map((issue) => (
                <li key={issue} className="text-[0.85rem] text-amber">
                  {issueText(issue)}
                </li>
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
    <div className="flex flex-wrap items-end gap-4 bg-[var(--wash)] px-6 py-6">
      <div className="w-56">
        <Field label="Vendor">
          <input className={inputClass} value={vendor} onChange={(e) => setVendor(e.target.value)} />
        </Field>
      </div>
      <div className="w-36">
        <Field label="Amount">
          <input className={`${inputClass} num`} value={amount} inputMode="decimal" onChange={(e) => setAmount(e.target.value)} />
        </Field>
      </div>
      <div className="w-36">
        <Field label="Tax">
          <input className={`${inputClass} num`} value={tax} inputMode="decimal" onChange={(e) => setTax(e.target.value)} />
        </Field>
      </div>
      <Button variant="primary" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </Button>
      <Button variant="ghost" onClick={onDone}>
        Cancel
      </Button>
    </div>
  );
}

export function TransactionTable({ rows }: { rows: Transaction[] }) {
  const { remove } = useApp();
  const { t } = useT();
  const categoryText = useCategoryText();
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="grid-table min-w-[900px]">
        <thead>
          <tr>
            <Th>{t("transactions.colVendor")}</Th>
            <Th width="130px">{t("transactions.colDate")}</Th>
            <Th width="150px">{t("transactions.colCategory")}</Th>
            <Th align="right" width="110px">{t("transactions.colTax")}</Th>
            <Th align="right" width="130px">{t("transactions.colAmount")}</Th>
            <Th align="right" width="110px">{t("transactions.colConfidence")}</Th>
            <Th width="150px" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const expanded = open === row.id;
            return (
              <Fragment key={row.id}>
                <tr
                  className={`selectable ${expanded ? "bg-[var(--wash)]" : ""}`}
                  onClick={() => setOpen(expanded ? null : row.id)}
                >
                  <td>
                    <div className="flex items-center gap-2.5">
                      <span className="font-medium text-ink">{row.vendor ?? "Unidentified"}</span>
                      {row.status === "needs_review" ? <Pill tone="review">Review</Pill> : null}
                      {row.status === "discarded" ? <Pill tone="neutral">Discarded</Pill> : null}
                    </div>
                  </td>
                  <td className="num text-ink-3">{shortDate(row.date)}</td>
                  <td className="text-ink-3">{categoryText(row.category)}</td>
                  <td className="num align-right text-ink-3">{money(row.tax)}</td>
                  <td className="num align-right font-medium text-ink">{money(row.amount)}</td>
                  <td className="num align-right text-ink-4">{Math.round((row.confidence ?? 0) * 100)}%</td>
                  <td>
                    <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setEditing(editing === row.id ? null : row.id);
                          setOpen(row.id);
                        }}
                      >
                        {t("common.edit")}
                      </Button>
                      <Button variant="ghost" onClick={() => remove(row.id)}>
                        {t("common.delete")}
                      </Button>
                    </div>
                  </td>
                </tr>
                {expanded ? (
                  <tr>
                    <td colSpan={7} className="!p-0">
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
