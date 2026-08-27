"use client";

import { useState } from "react";
import { money, moneyCompact, monthLabel } from "@/lib/format";

/* One measure, one hue. Identity lives in the axis labels, so there is no
   categorical palette to get wrong and no legend to read. */

function TableView({ rows, head }: { rows: { label: string; value: number }[]; head: [string, string] }) {
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="border-b border-line text-left text-[12px] text-ink-3">
          <th className="px-4 py-1.5 font-normal">{head[0]}</th>
          <th className="px-4 py-1.5 text-right font-normal">{head[1]}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className="border-b border-line last:border-0">
            <td className="px-4 py-1.5 text-ink-2">{row.label}</td>
            <td className="num px-4 py-1.5 text-right text-ink">{money(row.value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ViewToggle({ table, onToggle }: { table: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="text-[12px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
    >
      {table ? "Chart" : "Table"}
    </button>
  );
}

export function MonthlyBars({ data }: { data: { month: string; amount: number }[] }) {
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  if (!data.length) {
    return <p className="px-4 py-10 text-center text-[13px] text-ink-3">No dated receipts yet.</p>;
  }

  const rows = data.map((d) => ({ label: monthLabel(d.month), value: d.amount }));
  if (table) {
    return (
      <div>
        <div className="flex justify-end px-4 pt-2">
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
  const columns = { gridTemplateColumns: `repeat(${data.length}, minmax(0, 64px))` };

  return (
    <div className="px-4 pt-3 pb-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="num text-[12px] text-ink-3">
          peak {moneyCompact(data[peak].amount)}
        </span>
        <ViewToggle table={false} onToggle={() => setTable(true)} />
      </div>
      <div className="grid h-[132px] items-end gap-[2px]" style={columns}>
        {data.map((point, index) => {
          const height = Math.max(3, Math.round((point.amount / max) * 118));
          const active = hover === index;
          return (
            <div
              key={point.month}
              className="group relative flex flex-col items-center justify-end"
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            >
              {active && (
                <div className="pointer-events-none absolute bottom-[calc(100%+6px)] z-10 whitespace-nowrap rounded-[5px] border border-line bg-surface px-2 py-1 text-[12px] shadow-sm">
                  <span className="text-ink-3">{monthLabel(point.month)} </span>
                  <span className="num text-ink">{money(point.amount)}</span>
                </div>
              )}
              <div
                style={{ height }}
                className={`w-full rounded-t-[4px] transition-colors ${
                  active ? "bg-accent-ink" : "bg-accent"
                }`}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 grid gap-[2px] border-t border-line pt-1.5" style={columns}>
        {data.map((point) => (
          <span key={point.month} className="text-center text-[11px] text-ink-3">
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
    return <p className="px-4 py-10 text-center text-[13px] text-ink-3">{emptyLabel}</p>;
  }

  const rows = data.map((d) => ({ label: d.name, value: d.amount }));
  if (table) {
    return (
      <div>
        <div className="flex justify-end px-4 pt-2">
          <ViewToggle table onToggle={() => setTable(false)} />
        </div>
        <TableView rows={rows} head={["Category", "Spent"]} />
      </div>
    );
  }

  const max = Math.max(...data.map((d) => d.amount), 1);
  return (
    <div className="px-4 pt-3 pb-4">
      <div className="mb-2 flex justify-end">
        <ViewToggle table={false} onToggle={() => setTable(true)} />
      </div>
      <ul className="space-y-2">
        {data.map((row) => (
          <li key={row.name} className="group grid grid-cols-[110px_1fr_74px] items-center gap-3">
            <span className="truncate text-[13px] text-ink-2" title={row.name}>
              {row.name}
            </span>
            <span className="h-[9px] rounded-[3px] bg-canvas">
              <span
                className="block h-full rounded-[3px] bg-accent transition-colors group-hover:bg-accent-ink"
                style={{ width: `${Math.max(2, (row.amount / max) * 100)}%` }}
              />
            </span>
            <span className="num text-right text-[13px] text-ink">{money(row.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
