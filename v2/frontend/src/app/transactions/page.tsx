"use client";

import { useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { TransactionTable } from "@/components/TransactionTable";
import { Button, Card, Empty, inputClass } from "@/components/ui";
import { money } from "@/lib/format";

type Filter = "all" | "parsed" | "needs_review";

export default function TransactionsPage() {
  const { transactions, loading } = useApp();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return transactions.filter((row) => {
      if (row.status === "skipped") return false;
      if (filter !== "all" && row.status !== filter) return false;
      if (!needle) return true;
      return [row.vendor, row.category, row.order_number, row.payment_method]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [transactions, query, filter]);

  const total = rows.reduce((sum, row) => sum + (row.amount ?? 0), 0);

  const exportCsv = () => {
    const header = ["date", "vendor", "amount", "tax", "category", "status", "confidence"];
    const body = rows.map((row) =>
      [row.date, row.vendor, row.amount, row.tax, row.category, row.status, row.confidence]
        .map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...body].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "receipts.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader title="Transactions" description="Click any row to see how each field was decided." />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          className={`${inputClass} w-56`}
          placeholder="Search vendor, category, order…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="flex rounded-[5px] border border-line-strong bg-surface p-0.5">
          {(["all", "parsed", "needs_review"] as Filter[]).map((option) => (
            <button
              key={option}
              onClick={() => setFilter(option)}
              className={`rounded-[3px] px-2.5 py-1 text-[12px] transition-colors ${
                filter === option ? "bg-canvas font-medium text-ink" : "text-ink-3 hover:text-ink"
              }`}
            >
              {option === "needs_review" ? "Needs review" : option === "all" ? "All" : "Clean"}
            </button>
          ))}
        </div>
        <span className="num ml-auto text-[12px] text-ink-3">
          {rows.length} rows · {money(total)}
        </span>
        <Button size="sm" onClick={exportCsv} disabled={!rows.length}>
          Export CSV
        </Button>
      </div>

      <Card>
        {loading ? (
          <Empty title="Loading…" />
        ) : rows.length ? (
          <TransactionTable rows={rows} />
        ) : (
          <Empty title="No transactions match">Try clearing the search or running a sync.</Empty>
        )}
      </Card>
    </>
  );
}
