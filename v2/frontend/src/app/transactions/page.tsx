"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useApp } from "@/components/AppState";
import { PageHeader, Toolbar } from "@/components/Shell";
import { TransactionTable, useCategoryText } from "@/components/TransactionTable";
import { Button, Empty, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useT } from "@/lib/i18n";

export default function TransactionsPage() {
  return (
    <Suspense fallback={null}>
      <Transactions />
    </Suspense>
  );
}

function Transactions() {
  const { transactions, loading } = useApp();
  const { t } = useT();
  const categoryText = useCategoryText();
  const params = useSearchParams();
  // Arriving from an insight: `ids` pins the exact rows it was talking about,
  // `q` seeds the search box for a finding that names a vendor instead.
  const pinned = useMemo(() => {
    const raw = params.get("ids");
    return raw ? new Set(raw.split(",").filter(Boolean)) : null;
  }, [params]);
  const [query, setQuery] = useState(params.get("q") ?? "");
  // Dropdowns, not a tab strip: filtering is an attribute of the grid below,
  // so it should not look like another place to navigate to.
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");

  const categories = useMemo(
    () => Array.from(new Set(transactions.map((r) => r.category).filter(Boolean))).sort() as string[],
    [transactions],
  );

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return transactions.filter((row) => {
      if (pinned) return pinned.has(String(row.id));
      if (row.status === "skipped") return false;
      if (status !== "all" && row.status !== status) return false;
      if (category !== "all" && row.category !== category) return false;
      if (!needle) return true;
      return [row.vendor, row.category, row.order_number, row.payment_method]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [transactions, query, status, category, pinned]);

  const total = rows.reduce((sum, row) => sum + (row.amount ?? 0), 0);

  return (
    <>
      <PageHeader
        title={t("transactions.title")}
        description={t("transactions.description")}
      />

      {/* Pinning hides the usual filters' effect, so say so and offer a way out
          rather than leaving the grid looking mysteriously short. */}
      {pinned ? (
        <div className="mb-3 flex items-center gap-3 rounded-[10px] border border-[rgba(96,165,250,0.35)] bg-[rgba(96,165,250,0.08)] px-4 py-2.5 text-[0.85rem]">
          <span className="text-ink-2">
            {t(pinned.size === 1 ? "transactions.pinnedOne" : "transactions.pinned", { count: pinned.size })}
          </span>
          <Link href="/transactions" className="ml-auto text-accent hover:underline">
            {t("common.showAll")}
          </Link>
        </div>
      ) : null}

      <Toolbar>
        <input
          className="field w-[280px]"
          placeholder={t("transactions.search")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select className="field" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="all">{t("transactions.allStates")}</option>
          <option value="parsed">{t("transactions.settled")}</option>
          <option value="needs_review">{t("transactions.needsReview")}</option>
          <option value="discarded">{t("transactions.discarded")}</option>
        </select>
        <select className="field" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="all">{t("transactions.allCategories")}</option>
          {categories.map((option) => (
            <option key={option} value={option}>
              {categoryText(option)}
            </option>
          ))}
        </select>
        <span className="num ml-auto text-[0.85rem] text-ink-4">
          {t("common.rows", { count: rows.length, total: money(total) })}
        </span>
        <Button onClick={() => (window.location.href = api.exportUrl("ledger"))} disabled={!rows.length}>
          {t("common.exportCsv")}
        </Button>
      </Toolbar>

      <Panel flush>
        {loading ? (
          <Empty title={t("common.loading")} />
        ) : rows.length ? (
          <TransactionTable rows={rows} />
        ) : (
          <Empty title="Nothing matches">Clear the filters, or run a sync.</Empty>
        )}
      </Panel>
    </>
  );
}
