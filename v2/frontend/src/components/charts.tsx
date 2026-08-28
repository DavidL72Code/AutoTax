"use client";

import { useState } from "react";
import { money, moneyCompact, monthLabel } from "@/lib/format";

/* One measure, one hue. Identity is carried by the axis labels, so there is no
   categorical palette to misread and no legend to decode. Bars use v1's blue
   with the same inset highlight the buttons have, so they belong to the same
   surface language. */

function TableView({ rows, head }: { rows: { label: string; value: number }[]; head: [string, string] }) {
  return (
    <table className="grid-table">
      <thead>
        <tr>
          <th>{head[0]}</th>
          <th className="align-right">{head[1]}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td className="text-ink-2">{row.label}</td>
            <td className="num align-right text-ink">{money(row.value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ViewToggle({ table, onToggle }: { table: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="eyebrow transition-colors hover:text-ink-2">
      {table ? "Chart" : "Table"}
    </button>
  );
}

export function MonthlyBars({ data }: { data: { month: string; amount: number }[] }) {
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  if (!data.length) {
    return <p className="py-14 text-center text-[0.9rem] text-ink-3">No dated receipts yet.</p>;
  }

  const rows = data.map((d) => ({ label: monthLabel(d.month), value: d.amount }));
  if (table) {
    return (
      <div>
        <div className="mb-3 flex justify-end">
          <ViewToggle table onToggle={() => setTable(false)} />
        </div>
        <TableView rows={rows} head={["Month", "Spent"]} />
      </div>
    );
  }

  const max = Math.max(...data.map((d) => d.amount), 1);
  const peak = data.reduce((best, d, i) => (d.amount > data[best].amount ? i : best), 0);
  // Bars keep a sane width when only a couple of months exist, instead of
  // stretching into blocks that imply more data than there is.
  const columns = { gridTemplateColumns: `repeat(${data.length}, minmax(0, 72px))` };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="num text-[0.82rem] text-ink-4">peak {moneyCompact(data[peak].amount)}</span>
        <ViewToggle table={false} onToggle={() => setTable(true)} />
      </div>
      <div className="grid h-[172px] items-end gap-2" style={columns}>
        {data.map((point, index) => {
          const height = Math.max(4, Math.round((point.amount / max) * 158));
          const active = hover === index;
          return (
            <div
              key={point.month}
              className="relative flex flex-col items-center justify-end"
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            >
              {active && (
                <div className="pointer-events-none absolute bottom-[calc(100%+8px)] z-10 rounded-[10px] border border-line-strong bg-[#0e1526] px-2.5 py-1.5 whitespace-nowrap shadow-[0_10px_30px_rgba(2,6,23,0.6)]">
                  <span className="num text-[0.82rem] text-ink">{money(point.amount)}</span>
                </div>
              )}
              <div style={{ height }} className="bar w-full rounded-t-[8px]" />
            </div>
          );
        })}
      </div>
      <div className="mt-3 grid gap-2 border-t border-line pt-3" style={columns}>
        {data.map((point) => (
          <span key={point.month} className="num text-center text-[0.76rem] text-ink-4">
            {monthLabel(point.month)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function CategoryBars({
  data,
  emptyLabel = "Nothing categorised yet.",
}: {
  data: { name: string; amount: number }[];
  emptyLabel?: string;
}) {
  const [table, setTable] = useState(false);

  if (!data.length) {
    return <p className="py-14 text-center text-[0.9rem] text-ink-3">{emptyLabel}</p>;
  }

  const rows = data.map((d) => ({ label: d.name, value: d.amount }));
  if (table) {
    return (
      <div>
        <div className="mb-3 flex justify-end">
          <ViewToggle table onToggle={() => setTable(false)} />
        </div>
        <TableView rows={rows} head={["Name", "Spent"]} />
      </div>
    );
  }

  const max = Math.max(...data.map((d) => d.amount), 1);
  return (
    <div>
      <div className="mb-4 flex justify-end">
        <ViewToggle table={false} onToggle={() => setTable(true)} />
      </div>
      <ul className="space-y-3.5">
        {data.map((row) => (
          <li key={row.name} className="bar-track grid grid-cols-[130px_1fr_100px] items-center gap-4">
            <span className="truncate text-[0.9rem] text-ink-2" title={row.name}>
              {row.name}
            </span>
            <span className="h-2.5 rounded-full bg-[rgba(148,163,184,0.1)]">
              <span
                className="bar block h-full rounded-full"
                style={{ width: `${Math.max(2, (row.amount / max) * 100)}%` }}
              />
            </span>
            <span className="num text-right text-[0.9rem] text-ink">{money(row.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
