"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/components/AppState";
import { Button } from "@/components/ui";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/transactions", label: "Transactions" },
  { href: "/review", label: "Review" },
  { href: "/activity", label: "Activity" },
  { href: "/settings", label: "Settings" },
];

function RunTicker() {
  const { run } = useApp();
  if (!run || run.status === "done" || run.status === "failed") return null;
  const label = run.status === "fetching" ? "Reading inbox" : "Parsing";
  return (
    <span className="num flex items-center gap-2 text-[12px] text-ink-2">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      {label} {run.total ? `${run.done}/${run.total}` : ""}
    </span>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session, stats, startSync, connectGmail, run } = useApp();
  const syncing = Boolean(run && ["starting", "fetching", "parsing"].includes(run.status));

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-[212px] shrink-0 flex-col justify-between border-r border-line bg-surface px-3 py-4 md:flex">
        <div>
          <div className="px-2 pb-5">
            <span className="text-[14px] font-semibold tracking-[-0.01em] text-ink">Receipts</span>
            <span className="ml-1.5 text-[11px] text-ink-3">v2</span>
          </div>
          <nav className="space-y-0.5">
            {NAV.map((item) => {
              const active = pathname === item.href;
              const badge = item.href === "/review" ? stats?.needs_review ?? 0 : 0;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center justify-between rounded-[5px] px-2 py-1.5 text-[13px] transition-colors ${
                    active ? "bg-canvas font-medium text-ink" : "text-ink-2 hover:bg-canvas hover:text-ink"
                  }`}
                >
                  {item.label}
                  {badge > 0 ? <span className="num text-[11px] text-warn">{badge}</span> : null}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="px-2 text-[12px] text-ink-3">
          {session?.signed_in ? (
            <span className="block truncate" title={session.email ?? ""}>
              {session.email}
            </span>
          ) : (
            <span>Not connected</span>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[52px] items-center justify-between gap-4 border-b border-line bg-surface px-5">
          <nav className="flex items-center gap-3 md:hidden">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`text-[13px] ${pathname === item.href ? "text-ink" : "text-ink-3"}`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="hidden md:block" />
          <div className="flex items-center gap-3">
            <RunTicker />
            {session?.gmail_connected ? (
              <Button variant="primary" onClick={startSync} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync inbox"}
              </Button>
            ) : (
              <Button variant="primary" onClick={connectGmail}>
                Connect Gmail
              </Button>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1080px] flex-1 px-5 py-6">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-[19px] font-semibold tracking-[-0.015em] text-ink">{title}</h1>
      {description ? <p className="mt-0.5 text-[13px] text-ink-3">{description}</p> : null}
    </div>
  );
}
