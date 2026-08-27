"use client";

import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { Badge, Button, Card, Empty, StatTile } from "@/components/ui";
import { money } from "@/lib/format";

const NODES = [
  ["triage", "Decides whether an email is a purchase at all. Rules settle the clear cases; only ambiguous ones cost a model call."],
  ["extract", "Pulls totals, tax, subtotal, order number and card from the text with line-anchored patterns."],
  ["resolve", "Identifies the merchant. Sender domain outranks body text; payment processors defer to the body."],
  ["escalate", "The only node that spends a model call on extraction, and only for the fields the rules could not prove."],
  ["enrich", "Assigns a spending category — free for known merchants, model-assisted for the rest."],
  ["validate", "Checks the arithmetic: subtotal plus tax against the total, tax share, date sanity. Failures go back to escalate once."],
  ["persist", "Writes the record, or parks it for review when confidence is low."],
];

export default function ActivityPage() {
  const { run, liveRecords, startSync, startDemo, stopSync, session } = useApp();
  const running = Boolean(run && ["starting", "fetching", "parsing"].includes(run.status));

  return (
    <>
      <PageHeader title="Activity" description="What the pipeline is doing, email by email." />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        {session?.gmail_connected ? (
          <Button variant="primary" onClick={startSync} disabled={running}>
            {running ? "Running…" : "Sync inbox"}
          </Button>
        ) : null}
        <Button onClick={startDemo} disabled={running}>
          Run sample inbox
        </Button>
        {running ? (
          <Button variant="quiet" onClick={stopSync}>
            Stop
          </Button>
        ) : null}
        {run?.error ? <span className="text-[12px] text-danger">{run.error}</span> : null}
      </div>

      {run ? (
        <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="Status" value={<span className="text-[18px]">{run.status}</span>} />
          <StatTile label="Processed" value={`${run.done}/${run.total}`} />
          <StatTile label="Saved" value={run.saved} />
          <StatTile label="Flagged" value={run.review} hint={`${run.skipped} skipped as non-receipts`} />
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <Card title="Live results">
          {liveRecords.length ? (
            <ul>
              {liveRecords.map((record, index) => (
                <li key={`${record.email_id}-${index}`} className="border-b border-line px-4 py-3 last:border-0">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] text-ink">{record.vendor ?? "Unidentified"}</span>
                      {record.status !== "parsed" ? <Badge tone={record.status}>{record.status.replace("_", " ")}</Badge> : null}
                    </div>
                    <span className="num text-[13px] text-ink">{money(record.amount)}</span>
                  </div>
                  <ol className="mt-1.5 space-y-0.5">
                    {record.steps.map((step, stepIndex) => (
                      <li key={`${step.node}-${stepIndex}`} className="flex gap-2 text-[12px]">
                        <span className="w-[62px] shrink-0 font-mono text-ink-3">{step.node}</span>
                        <span className="flex-1 text-ink-2">{step.detail}</span>
                        <span className="num shrink-0 text-ink-3">{step.ms}ms</span>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title={running ? "Waiting on the first result…" : "No run in progress"}>
              Start a sync, or run the sample inbox to watch the graph work.
            </Empty>
          )}
        </Card>

        <Card title="The pipeline">
          <ol className="px-4 py-3">
            {NODES.map(([name, description], index) => (
              <li key={name} className="relative pb-4 pl-5 last:pb-0">
                {index < NODES.length - 1 ? (
                  <span className="absolute top-[14px] bottom-0 left-[3px] w-px bg-line" />
                ) : null}
                <span className="absolute top-[5px] left-0 h-[7px] w-[7px] rounded-full bg-accent" />
                <div className="font-mono text-[12px] text-ink">{name}</div>
                <p className="mt-0.5 text-[12px] leading-[1.45] text-ink-3">{description}</p>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </>
  );
}
