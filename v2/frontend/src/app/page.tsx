"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { CategoryBars, MonthlyBars } from "@/components/charts";
import { GraphDiagram } from "@/components/GraphDiagram";
import { useCategoryText } from "@/components/TransactionTable";
import { useT, useTrace } from "@/lib/i18n";
import { PageHeader } from "@/components/Shell";
import { Button, Empty, Panel, Pill, Stat, StepScore } from "@/components/ui";
import { money, shortDate } from "@/lib/format";

/* The front door. The work happens here — a run streams through the graph in
   the open — and the summary sits underneath it. Previously these were two
   pages, "Overview" and "Activity", and the one that actually did something
   was the one nobody could find. */

function Onboarding() {
  const { connectGmail, startDemo, session } = useApp();
  return (
    <Panel>
      <div className="py-4">
        <h2 className="font-[family-name:var(--font-display)] text-[1.35rem] font-bold tracking-[-0.02em] text-ink">
          Start with your inbox
        </h2>
        <p className="mt-3 max-w-xl text-[0.95rem] leading-relaxed text-ink-3">
          Signing in with Google grants read-only Gmail access. Receipts are parsed on your server, the refresh
          token is encrypted at rest, and nothing is written back to your mailbox.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button variant="primary" onClick={connectGmail}>
            Sign in with Google
          </Button>
          <Button onClick={startDemo}>Run a sample inbox instead</Button>
        </div>
        {session && !session.model_configured ? (
          <p className="mt-6 text-[0.85rem] text-amber">
            No model key configured — parsing runs on rules alone, which resolves most vendors but misses
            totals on awkward layouts.
          </p>
        ) : null}
      </div>
    </Panel>
  );
}

/** The live run: counters, then every email as the graph finishes with it. */
function Processing() {
  const { run, liveRecords, stopSync, startDemo, session } = useApp();
  const { t } = useT();
  const trace = useTrace();
  const active = Boolean(run && ["starting", "fetching", "parsing"].includes(run.status));

  // Always rendered once you are signed in: the diagram is how you learn what
  // the app does, so it should not be hidden behind having run something.
  return (
    <div className="mb-4">
      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label={t("dashboard.runStatus")}
          value={<span className="text-[1.4rem]">{run?.status ?? t("dashboard.idle")}</span>}
          sub={run?.total ? t("dashboard.progress", { done: run.done, total: run.total }) : t("dashboard.noEmails")}
        />
        <Stat label={t("dashboard.saved")} value={run?.saved ?? 0} sub={t("dashboard.savedSub")} />
        <Stat
          label={t("dashboard.paused")}
          value={run?.review ?? 0}
          tone={run?.review ? "accent" : "neutral"}
          sub={
            run?.review ? (
              <Link href="/review" className="text-amber hover:underline">
                {t("dashboard.resume")}
              </Link>
            ) : (
              t("dashboard.nothingWaiting")
            )
          }
        />
        <Stat label={t("dashboard.skipped")} value={run?.skipped ?? 0} sub={t("dashboard.skippedSub")} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title={t("dashboard.graphTitle")} flush>
          <GraphDiagram records={liveRecords} active={active} />
        </Panel>

        <Panel
          title={t("dashboard.processing")}
          flush
          action={
            active ? (
              <button onClick={stopSync} className="text-[0.8rem] text-ink-4 hover:text-ink-2">
                Stop
              </button>
            ) : (
              <button onClick={startDemo} className="text-[0.8rem] text-ink-4 hover:text-ink-2">
                {session?.gmail_connected ? t("common.runSample") : t("common.runAgain")}
              </button>
            )
          }
        >
          {liveRecords.length ? (
            <ul className="max-h-[520px] overflow-y-auto">
              {liveRecords.map((record, index) => (
                <li
                  key={`${record.email_id}-${index}`}
                  className="border-b border-[var(--hairline)] px-6 py-4 last:border-0"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span className="font-medium text-ink">{record.vendor ?? "Unidentified"}</span>
                      {record.status !== "parsed" ? (
                        <Pill tone={record.status === "needs_review" ? "review" : "neutral"}>
                          {record.status.replace("_", " ")}
                        </Pill>
                      ) : null}
                    </div>
                    <span className="num font-medium text-ink">{money(record.amount)}</span>
                  </div>
                  <ol className="mt-2.5 space-y-1.5">
                    {record.steps.map((step, stepIndex) => (
                      <li key={`${step.node}-${stepIndex}`} className="flex gap-3 text-[0.82rem]">
                        <span className="num w-[100px] shrink-0 text-ink-4">{step.node}</span>
                        <span className="flex-1 text-ink-3">{trace(step)}</span>
                        <StepScore value={step.confidence} />
                        <span className="num shrink-0 text-ink-4">{step.ms}ms</span>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title={active ? "Waiting on the first result…" : "Run finished"}>
              Each email shows every step the graph took to reach its numbers.
            </Empty>
          )}
        </Panel>

      </div>
    </div>
  );
}

export default function DashboardPage() {
  const categoryText = useCategoryText();
  const { t } = useT();
  const { session, stats, transactions, run, loading, error } = useApp();

  if (loading) return <p className="text-[0.9rem] text-ink-3">{t("common.loading")}</p>;

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Panel flush>
          <Empty title="Can't reach the API">
            {error}. Start the backend with <span className="num">v2/backend/run.sh</span>, and check{" "}
            <span className="num">NEXT_PUBLIC_API_BASE</span> matches the port it is serving on.
          </Empty>
        </Panel>
      </>
    );
  }

  if (!session?.signed_in || (!stats?.receipt_count && !run)) {
    return (
      <>
        <PageHeader title="Dashboard" description="Receipts pulled from email, parsed and checked." />
        <Onboarding />
      </>
    );
  }

  const recent = transactions.filter((row) => row.status !== "skipped").slice(0, 7);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Runs stream here as they happen. Everything below is the ledger they produced."
      />

      <Processing />

      {stats?.receipt_count ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Total spent" value={money(stats.total_spent)} sub={`${stats.receipt_count} receipts`} />
            <Stat label="Vendors" value={stats.vendor_count} sub="Distinct merchants" />
            <Stat label="Average" value={money(stats.average)} sub="Per receipt" />
            <Stat
              label="Needs review"
              value={stats.needs_review}
              tone={stats.needs_review ? "accent" : "neutral"}
              sub={
                stats.needs_review ? (
                  <Link href="/review" className="text-accent-soft hover:underline">
                    Resume paused threads
                  </Link>
                ) : (
                  "Everything reconciled"
                )
              }
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Panel title="Spend by month">
              <MonthlyBars data={stats.by_month} />
            </Panel>
            <Panel title="By category">
              <CategoryBars data={stats.by_category} />
            </Panel>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Panel title="Top vendors">
              <CategoryBars data={stats.top_vendors} emptyLabel="No vendors yet." />
            </Panel>
            <Panel
              title="Recent"
              flush
              action={
                <Link href="/transactions" className="eyebrow transition-colors hover:text-ink-2">
                  All
                </Link>
              }
            >
              {recent.length ? (
                <ul>
                  {recent.map((row) => (
                    <li
                      key={row.id}
                      className="flex items-center justify-between gap-4 border-b border-[var(--hairline)] px-6 py-4 last:border-0"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2.5">
                          <span className="truncate font-medium text-ink">{row.vendor ?? "Unidentified"}</span>
                          {row.status === "needs_review" ? <Pill tone="review">Review</Pill> : null}
                        </div>
                        <div className="mt-1 text-[0.82rem] text-ink-4">
                          {shortDate(row.date)} · {categoryText(row.category)}
                        </div>
                      </div>
                      <span className="num shrink-0 font-medium text-ink">{money(row.amount)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Nothing parsed yet" />
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </>
  );
}
