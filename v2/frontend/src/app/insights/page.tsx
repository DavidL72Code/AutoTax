"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { Empty, Panel, Pill, Stat, Th } from "@/components/ui";
import { Insights, api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { money, shortDate } from "@/lib/format";

const CADENCE_LABEL: Record<string, string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  monthly: "Monthly",
  bimonthly: "Every 2 months",
  quarterly: "Quarterly",
  semiannual: "Twice a year",
  annual: "Yearly",
};

export default function InsightsPage() {
  const { t } = useT();
  /* A finding arrives as a kind plus the values its sentence needs. If a locale
     has no phrasing for that kind we fall back to the English the backend
     built, rather than showing a bare key. */
  const say = (f: { kind: string; title: string; detail: string; params?: Record<string, unknown> }, part: "title" | "detail") => {
    const key = `finding.${f.kind}.${part}`;
    // Money arrives as a bare number so the locale decides the formatting; the
    // English sentence used to bake in "$%.2f", and a raw 41.2 in its place
    // reads as a bug.
    const MONEY = ["amount", "typical", "latest", "baseline", "annual_delta"];
    const params = Object.fromEntries(
      Object.entries(f.params ?? {}).map(([k, v]) =>
        MONEY.includes(k) && typeof v === "number" ? [k, money(v)] : [k, v],
      ),
    );
    const text = t(key, params);
    return text === key ? f[part] : text;
  };
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.insights());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load insights");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <Panel flush>
        <Empty title="Nothing to analyse yet">{error}</Empty>
      </Panel>
    );
  }
  if (!data) return <p className="text-[0.9rem] text-ink-3">{t("common.loading")}</p>;

  const { subscriptions, subscription_summary: summary, anomalies, concentration } = data;
  const urgent = anomalies.filter((a) => a.severity === "action").length;

  return (
    <>
      <PageHeader
        title={t("insights.title")}
        description={t("insights.description")}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label={t("insights.commitment")}
          value={money(summary.annual_commitment)}
          sub={t("insights.commitmentSub", { monthly: money(summary.monthly_equivalent), vendors: summary.count })}
        />
        <Stat
          label={t("insights.priceIncreases")}
          value={summary.price_increases.length}
          tone={summary.price_increases.length ? "accent" : "neutral"}
          sub={t("insights.priceIncreasesSub")}
        />
        <Stat
          label={t("insights.needsChecking")}
          value={urgent}
          tone={urgent ? "accent" : "neutral"}
          sub={t("insights.findingsTotal", { count: anomalies.length })}
        />
        <Stat
          label={t("insights.concentration")}
          value={`${concentration.top_share_pct}%`}
          sub={t("insights.concentrationSub", { vendors: concentration.vendors })}
        />
      </div>

      <Panel title={t("insights.worthALook")} flush className="mt-4">
        {anomalies.length ? (
          <ul>
            {anomalies.map((finding, index) => (
              <li
                key={`${finding.kind}-${index}`}
                className="border-b border-[var(--hairline)] px-6 py-4 last:border-0"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <Pill tone={finding.severity === "action" ? "review" : "neutral"}>
                      {finding.severity === "action" ? t("insights.check") : t("insights.watch")}
                    </Pill>
                    <span className="font-medium text-ink">{say(finding, "title")}</span>
                  </div>
                  <span className="num text-ink-2">{money(finding.amount)}</span>
                </div>
                <p className="mt-1.5 text-[0.85rem] leading-relaxed text-ink-3">{say(finding, "detail")}</p>
                {/* A finding names rows or a vendor; either way it should be
                    possible to go and look rather than take its word. */}
                {finding.transaction_ids.length ? (
                  <Link
                    href={`/transactions?ids=${encodeURIComponent(finding.transaction_ids.join(","))}`}
                    className="mt-2 inline-block text-[0.82rem] text-accent hover:underline"
                  >
                    {t(
                      finding.transaction_ids.length === 1
                        ? "insights.showReceipt"
                        : "insights.showReceipts",
                      { count: finding.transaction_ids.length },
                    )}
                  </Link>
                ) : finding.vendor ? (
                  <Link
                    href={`/transactions?q=${encodeURIComponent(finding.vendor)}`}
                    className="mt-2 inline-block text-[0.82rem] text-accent hover:underline"
                  >
                    {t("insights.showVendor", { vendor: finding.vendor })}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <Empty title={t("insights.nothingAnomalous")}>
            {t("insights.nothingAnomalousSub")}
          </Empty>
        )}
      </Panel>

      <Panel title={t("insights.recurring")} flush className="mt-4">
        {subscriptions.length ? (
          <div className="overflow-x-auto">
            <table className="grid-table min-w-[860px]">
              <thead>
                <tr>
                  <Th>Vendor</Th>
                  <Th width="190px">Cadence</Th>
                  <Th align="right" width="120px">Typical</Th>
                  <Th align="right" width="120px">Latest</Th>
                  <Th align="right" width="130px">Per year</Th>
                  <Th width="140px">Next expected</Th>
                </tr>
              </thead>
              <tbody>
                {subscriptions.map((sub) => (
                  <tr key={sub.vendor}>
                    <td>
                      <div className="flex items-center gap-2.5">
                        <span className="font-medium text-ink">{sub.vendor}</span>
                        {sub.price_change_pct > 0 ? <Pill tone="review">+{sub.price_change_pct}%</Pill> : null}
                        {sub.days_overdue > sub.interval_days ? <Pill tone="neutral">Lapsed</Pill> : null}
                      </div>
                    </td>
                    <td className="text-ink-3">
                      {CADENCE_LABEL[sub.cadence] ?? sub.cadence}
                      <span className="num text-ink-4"> · {sub.charges}×</span>
                    </td>
                    <td className="num align-right text-ink-3">{money(sub.typical_amount)}</td>
                    <td className="num align-right text-ink-2">{money(sub.latest_amount)}</td>
                    <td className="num align-right font-medium text-ink">{money(sub.annualised)}</td>
                    <td className="num text-ink-3">{shortDate(sub.next_expected)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No recurring pattern yet">
            A charge counts as recurring once the same vendor bills at a steady interval, so this fills in
            after a couple of months of history.
          </Empty>
        )}
      </Panel>
    </>
  );
}
