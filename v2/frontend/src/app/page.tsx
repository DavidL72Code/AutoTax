"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { CategoryBars, MonthlyBars } from "@/components/charts";
import { PageHeader } from "@/components/Shell";
import { Badge, Button, Card, Empty, StatTile } from "@/components/ui";
import { money, shortDate } from "@/lib/format";

function Onboarding() {
  const { connectGmail, startDemo, session } = useApp();
  return (
    <Card>
      <div className="px-5 py-6">
        <h2 className="text-[15px] font-medium text-ink">Start with your inbox</h2>
        <p className="mt-1 max-w-lg text-[13px] text-ink-2">
          Connecting Gmail grants read-only access. Receipts are parsed on your server, the refresh
          token is encrypted at rest, and nothing is written back to your mailbox.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={connectGmail}>
            Connect Gmail
          </Button>
          <Button onClick={startDemo}>Run a sample inbox instead</Button>
        </div>
        {session && !session.model_configured ? (
          <p className="mt-4 text-[12px] text-warn">
            No model key configured — parsing will run on rules alone, which resolves most vendors
            but misses totals on awkward layouts.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

export default function OverviewPage() {
  const { session, stats, transactions, loading, error } = useApp();

  if (loading) {
    return <p className="text-[13px] text-ink-3">Loading…</p>;
  }

  if (error) {
    return (
      <Card>
        <Empty title="Can't reach the API">
          {error}. Start the backend with <code className="font-mono text-[12px]">v2/backend/run.sh</code>.
        </Empty>
      </Card>
    );
  }

  if (!session?.signed_in || !stats?.receipt_count) {
    return (
      <>
        <PageHeader title="Overview" description="Receipts pulled from email, parsed and checked." />
        <Onboarding />
      </>
    );
  }

  const recent = transactions.filter((row) => row.status !== "skipped").slice(0, 6);

  return (
    <>
      <PageHeader title="Overview" description="Receipts pulled from email, parsed and checked." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Total spent" value={money(stats.total_spent)} />
        <StatTile label="Receipts" value={stats.receipt_count} hint={`${stats.vendor_count} vendors`} />
        <StatTile label="Average" value={money(stats.average)} />
        <StatTile
          label="Needs review"
          value={stats.needs_review}
          hint={
            stats.needs_review > 0 ? (
              <Link href="/review" className="text-warn underline-offset-2 hover:underline">
                Resolve now
              </Link>
            ) : (
              "Everything reconciled"
            )
          }
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card title="Spend by month">
          <MonthlyBars data={stats.by_month} />
        </Card>
        <Card title="By category">
          <CategoryBars data={stats.by_category} />
        </Card>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card title="Top vendors">
          <CategoryBars data={stats.top_vendors} emptyLabel="No vendors yet." />
        </Card>
        <Card
          title="Recent"
          action={
            <Link href="/transactions" className="text-[12px] text-ink-3 underline-offset-2 hover:text-ink hover:underline">
              All transactions
            </Link>
          }
        >
          {recent.length ? (
            <ul>
              {recent.map((row) => (
                <li
                  key={row.id}
                  className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 last:border-0"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] text-ink">{row.vendor ?? "Unknown"}</span>
                      {row.status === "needs_review" ? <Badge tone="needs_review">review</Badge> : null}
                    </div>
                    <div className="text-[12px] text-ink-3">
                      {shortDate(row.date)} · {row.category ?? "Uncategorised"}
                    </div>
                  </div>
                  <span className="num shrink-0 text-[13px] text-ink">{money(row.amount)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="Nothing parsed yet" />
          )}
        </Card>
      </div>
    </>
  );
}
