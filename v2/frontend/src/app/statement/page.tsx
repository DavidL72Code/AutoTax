"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader, Toolbar } from "@/components/Shell";
import { Button, Delta, Empty, Panel, Stat, Th } from "@/components/ui";
import { Statement, TaxSummary, api } from "@/lib/api";
import { useCategoryText } from "@/components/TransactionTable";
import { useT } from "@/lib/i18n";
import { money, shortDate } from "@/lib/format";

function monthName(month: string): string {
  const parsed = new Date(`${month}-01T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? month
    : parsed.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export default function StatementPage() {
  const { t } = useT();
  const categoryText = useCategoryText();
  const [statement, setStatement] = useState<Statement | null>(null);
  const [tax, setTax] = useState<TaxSummary | null>(null);
  const [month, setMonth] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (target?: string) => {
    try {
      const next = await api.statement(target);
      setStatement(next);
      setMonth(next.month);
      setTax(await api.taxSummary(Number(next.month.slice(0, 4))));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("statement.failed"));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <Panel flush>
        <Empty title={t("statement.none")}>{error}</Empty>
      </Panel>
    );
  }
  if (!statement) return <p className="text-[0.9rem] text-ink-3">{t("common.loading")}</p>;

  const download = (shape: "ledger" | "journal" | "expenses") => {
    window.location.href = api.exportUrl(shape, month);
  };

  return (
    <>
      <PageHeader
        title={t("statement.title")}
        description={t("statement.headerDescription")}
      />

      <Toolbar>
        <select className="field" value={month} onChange={(event) => load(event.target.value)}>
          {(statement.available_months.length ? statement.available_months : [statement.month]).map((option) => (
            <option key={option} value={option}>
              {monthName(option)}
            </option>
          ))}
        </select>
        <span className="eyebrow ml-auto">{t("statement.export")}</span>
        <Button onClick={() => download("ledger")}>{t("statement.ledger")}</Button>
        <Button onClick={() => download("journal")}>{t("statement.journal")}</Button>
        <Button onClick={() => download("expenses")}>{t("statement.expenseClaim")}</Button>
      </Toolbar>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label={monthName(statement.month)}
          value={money(statement.total)}
          sub={
            statement.delta_pct === null ? (
              t("statement.receiptsCount", { count: statement.receipts })
            ) : (
              <span className="flex flex-wrap items-center gap-2">
                <Delta value={statement.delta} format={money} />
                <span>vs {money(statement.prior_total)}</span>
              </span>
            )
          }
        />
        <Stat label={t("statement.perDay")} value={money(statement.per_day)} sub={t("statement.receiptsCount", { count: statement.receipts })} />
        <Stat
          label={t(statement.projected ? "statement.projected" : "statement.salesTax")}
          value={money(statement.projected ?? statement.tax_paid)}
          sub={t(statement.projected ? "statement.perDaySub" : "statement.salesTaxSub")}
        />
        <Stat
          label={t("statement.largest")}
          value={money(statement.largest?.amount ?? 0)}
          sub={statement.largest ? `${statement.largest.vendor} · ${shortDate(statement.largest.date)}` : "-"}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title={t("statement.byCategory")} flush>
          {statement.categories.length ? (
            <table className="grid-table">
              <thead>
                <tr>
                  <Th>{t("statement.category")}</Th>
                  <Th align="right">{t("statement.thisMonth")}</Th>
                  <Th align="right">{t("statement.change")}</Th>
                  <Th align="right" width="90px">{t("statement.share")}</Th>
                </tr>
              </thead>
              <tbody>
                {statement.categories.map((row) => (
                  <tr key={row.name}>
                    <td className="text-ink-2">{categoryText(row.name)}</td>
                    <td className="num align-right font-medium text-ink">{money(row.amount)}</td>
                    <td className="align-right">
                      <Delta value={row.delta} format={money} />
                    </td>
                    <td className="num align-right text-ink-4">{row.share}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty title={t("statement.noSpend")} />
          )}
        </Panel>

        <Panel title={t("statement.taxTitle", { year: tax?.year ?? "" })} flush>
          {tax ? (
            <>
              <div className="grid grid-cols-3 border-b border-[var(--hairline)]">
                <div className="border-r border-[var(--hairline)] px-6 py-5">
                  <div className="eyebrow">{t("statement.salesTaxShort")}</div>
                  <div className="num mt-2 text-[1.35rem] text-ink">{money(tax.sales_tax_paid)}</div>
                </div>
                <div className="border-r border-[var(--hairline)] px-6 py-5">
                  <div className="eyebrow">{t("statement.effectiveRate")}</div>
                  <div className="num mt-2 text-[1.35rem] text-ink">{tax.effective_tax_rate}%</div>
                </div>
                <div className="px-6 py-5">
                  <div className="eyebrow">{t("statement.apportioned")}</div>
                  <div className="num mt-2 text-[1.35rem] text-ink">{money(tax.business_apportioned)}</div>
                </div>
              </div>
              <table className="grid-table">
                <thead>
                  <tr>
                    <Th>{t("statement.account")}</Th>
                    <Th align="right">{t("statement.gross")}</Th>
                    <Th align="right">{t("transactions.colTax")}</Th>
                    <Th align="right">{t("statement.claimable")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {tax.by_category.map((row) => (
                    <tr key={row.category}>
                      <td className="text-ink-2">
                        <span className="num text-ink-4">{row.account}</span> {row.account_name}
                      </td>
                      <td className="num align-right text-ink-3">{money(row.gross)}</td>
                      <td className="num align-right text-ink-4">{money(row.tax)}</td>
                      <td className="num align-right font-medium text-ink">{money(row.business_apportioned)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-[var(--hairline)] px-6 py-4 text-[0.8rem] text-ink-4">
                {tax.disclaimer}
              </p>
            </>
          ) : (
            <Empty title={t("statement.noTax")} />
          )}
        </Panel>
      </div>
    </>
  );
}
