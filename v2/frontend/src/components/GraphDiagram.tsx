"use client";

import { useMemo } from "react";
import { Transaction } from "@/lib/api";

/* The graph, drawn as the graph — with live traffic on it.
   Every node shows how many receipts have passed through it this run and how
   long it spent there on average, so a slow or unused step is visible rather
   than something you have to read a log to notice. */

const W = 680;
const H = 600;
const NODE_W = 160;
const NODE_H = 46;

type Node = {
  id: string;
  x: number;
  y: number;
  label: string;
  model?: boolean;
  terminal?: boolean;
  hint: string;
};

const NODES: Node[] = [
  { id: "_source", x: 250, y: 6, label: "Gmail message", terminal: true, hint: "Sender, subject, date, flattened body" },
  { id: "triage", x: 250, y: 76, label: "triage", model: true, hint: "Is this a purchase at all? Rules first; the model only when they are unsure." },
  { id: "extract", x: 250, y: 146, label: "extract", hint: "Total, tax, subtotal, order number, card. Line-anchored patterns." },
  { id: "resolve", x: 250, y: 216, label: "resolve", hint: "Which merchant was paid. Learned memory, then sender domain, then body." },
  { id: "escalate", x: 40, y: 216, label: "escalate", model: true, hint: "Asks the model, for the unproven fields only. Skipped when nothing is missing." },
  { id: "enrich", x: 250, y: 286, label: "enrich", model: true, hint: "Category and payment method. Free for a merchant already known." },
  { id: "validate", x: 250, y: 356, label: "validate", hint: "Subtotal plus tax against the total, tax share, positive amount, sane date." },
  { id: "await_review", x: 460, y: 356, label: "await_review", hint: "interrupt(). The thread is checkpointed and waits for a person." },
  { id: "persist", x: 250, y: 426, label: "persist", hint: "Writes the record, and stores whatever a correction taught it." },
  { id: "_ledger", x: 250, y: 496, label: "Ledger", terminal: true, hint: "Firestore, plus the learned rules" },
];

type Edge = { d: string; tone?: "normal" | "loop" | "human"; label?: string; lx?: number; ly?: number };

const EDGES: Edge[] = [
  { d: `M330,52 V${76 - 6}` },
  { d: `M330,122 V${146 - 6}` },
  { d: `M330,192 V${216 - 6}` },
  // triage rejects a non-receipt outright — nothing is stored.
  { d: "M250,99 H196", tone: "loop", label: "not a receipt", lx: 190, ly: 96 },
  // resolve → escalate when fields are still missing
  { d: "M250,239 H206", label: "gaps", lx: 228, ly: 232 },
  // escalate rejoins at enrich
  { d: "M120,262 V309 H244" },
  // resolve → enrich when nothing is missing
  { d: "M330,262 V280", label: "complete", lx: 340, ly: 276 },
  { d: `M330,332 V${356 - 6}` },
  { d: `M330,402 V${426 - 6}`, label: "clean", lx: 340, ly: 418 },
  // validate → await_review, and the human's answer coming back
  { d: "M410,372 H454", tone: "human", label: "unresolved", lx: 414, ly: 366 },
  { d: "M456,392 H416", tone: "human" },
  // the model retry loop, bounded to two attempts
  { d: "M250,392 H160 V268", tone: "loop", label: "retry ×2", lx: 166, ly: 330 },
  { d: `M330,472 V${496 - 6}` },
];

const TONE_COLOR = { normal: "rgba(148,163,184,0.32)", loop: "rgba(251,191,36,0.45)", human: "rgba(96,165,250,0.55)" };

export function GraphDiagram({
  records,
  active,
  activeNodes,
}: {
  records: Transaction[];
  active: boolean;
  /** Email id -> the node it last cleared, one entry per email still in
      flight. Absent outside a live run. */
  activeNodes?: Record<string, string>;
}) {
  const traffic = useMemo(() => {
    const acc: Record<string, { count: number; ms: number }> = {};
    for (const record of records) {
      for (const step of record.steps ?? []) {
        acc[step.node] ??= { count: 0, ms: 0 };
        acc[step.node].count += 1;
        acc[step.node].ms += step.ms;
      }
    }
    return acc;
  }, [records]);

  /* Where the run actually is.

     This used to be `records[0].steps.at(-1)` — the last step of the most
     recently *finished* email, which is `persist` by definition, so the
     highlight sat on the final node for the whole run.

     Sixteen emails run concurrently, so there is no single current step. A
     binary highlight lights every node at once and says nothing. Counting how
     many emails are sitting at each step does say something, and collapses to
     one obvious highlight when only one email is in flight. */
  const inFlight = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of Object.values(activeNodes ?? {})) {
      counts[node] = (counts[node] ?? 0) + 1;
    }
    return counts;
  }, [activeNodes]);

  const totals = useMemo(() => {
    const parsed = records.filter((r) => r.status === "parsed").length;
    const review = records.filter((r) => r.status === "needs_review").length;
    const skipped = records.filter((r) => r.status === "skipped").length;
    return { parsed, review, skipped };
  }, [records]);

  return (
    <div className="px-4 py-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Receipt parsing graph with live traffic">
        <defs>
          {(["normal", "loop", "human"] as const).map((tone) => (
            <marker
              key={tone}
              id={`gd-arrow-${tone}`}
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill={TONE_COLOR[tone]} />
            </marker>
          ))}
          <linearGradient id="gd-node" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--node-a)" />
            <stop offset="1" stopColor="var(--node-b)" />
          </linearGradient>
          <linearGradient id="gd-node-model" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--node-live-a)" />
            <stop offset="1" stopColor="var(--node-live-b)" />
          </linearGradient>
        </defs>

        {EDGES.map((edge, index) => {
          const tone = edge.tone ?? "normal";
          return (
            <g key={index}>
              <path
                d={edge.d}
                fill="none"
                stroke={TONE_COLOR[tone]}
                strokeWidth="1.4"
                strokeDasharray={tone === "normal" ? undefined : "5 4"}
                markerEnd={`url(#gd-arrow-${tone})`}
              />
              {edge.label ? (
                <text x={edge.lx} y={edge.ly} fontSize="10.5" fill="var(--color-ink-4)" textAnchor={edge.lx! < 250 ? "end" : "start"}>
                  {edge.label}
                </text>
              ) : null}
            </g>
          );
        })}

        {NODES.map((node) => {
          const seen = traffic[node.id];
          const here = active ? (inFlight[node.id] ?? 0) : 0;
          const isLatest = here > 0;
          const touched = Boolean(seen?.count);
          const stroke = isLatest
            ? "#60a5fa"
            : node.model
              ? "rgba(96,165,250,0.4)"
              : touched
                ? "rgba(148,163,184,0.4)"
                : "rgba(148,163,184,0.18)";

          return (
            <g key={node.id} opacity={node.terminal || touched || !records.length ? 1 : 0.55}>
              <title>{node.hint}</title>
              {isLatest ? (
                <rect
                  x={node.x - 3}
                  y={node.y - 3}
                  width={NODE_W + 6}
                  height={NODE_H + 6}
                  rx="13"
                  fill="none"
                  stroke="rgba(96,165,250,0.35)"
                  strokeWidth="2"
                >
                  <animate attributeName="opacity" values="0.9;0.25;0.9" dur="1.6s" repeatCount="indefinite" />
                </rect>
              ) : null}
              {isLatest && here > 1 ? (
                <text
                  x={node.x - 9}
                  y={node.y + NODE_H / 2 + 4}
                  fontSize="11"
                  textAnchor="end"
                  fill="var(--color-accent)"
                  fontFamily="var(--font-plex-mono), monospace"
                >
                  {here}
                </text>
              ) : null}

              <rect
                x={node.x}
                y={node.y}
                width={NODE_W}
                height={NODE_H}
                rx="11"
                fill={node.terminal ? "var(--node-terminal)" : node.model ? "url(#gd-node-model)" : "url(#gd-node)"}
                stroke={stroke}
                strokeWidth={isLatest ? 1.6 : 1}
                strokeDasharray={node.terminal ? "4 3" : undefined}
              />

              <text
                x={node.x + 12}
                y={node.y + (seen ? 20 : 28)}
                fontSize={node.terminal ? "11.5" : "12.5"}
                fill={node.terminal ? "var(--color-ink-3)" : "var(--color-ink)"}
                fontFamily={node.terminal ? "inherit" : "var(--font-plex-mono), monospace"}
              >
                {node.label}
              </text>

              {seen ? (
                <text
                  x={node.x + 12}
                  y={node.y + 35}
                  fontSize="10.5"
                  fill="var(--color-ink-4)"
                  fontFamily="var(--font-plex-mono), monospace"
                >
                  {seen.count}× · {Math.round(seen.ms / seen.count)}ms avg
                </text>
              ) : null}

              {node.model ? (
                <circle cx={node.x + NODE_W - 14} cy={node.y + 14} r="3.5" fill="var(--color-accent)" />
              ) : null}
            </g>
          );
        })}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--hairline)] pt-3 text-[0.78rem] text-ink-4">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-accent" /> may call the model
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-px w-4 bg-[rgba(251,191,36,0.6)]" /> retry loop
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-px w-4 bg-[rgba(96,165,250,0.7)]" /> human loop
        </span>
        {records.length ? (
          <span className="num ml-auto">
            {totals.parsed} saved · {totals.review} paused · {totals.skipped} skipped
          </span>
        ) : null}
      </div>
    </div>
  );
}
