"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { Lockup } from "@/components/Brand";
import { TopBar } from "@/components/TopBar";
import { useT } from "@/lib/i18n";

/* The rail owns navigation and the sync action. The bar above owns the two
   things that follow you around regardless of page — the bell and the account.
   Neither duplicates the other. */

type Item = { href: string; key: string; badge?: boolean };

/* Five destinations, each doing one job. "Overview" and "Activity" used to be
   two pages describing the same run from different angles; they are now one
   dashboard. */
const SECTIONS: { key: string; items: Item[] }[] = [
  {
    key: "nav.workspace",
    items: [
      { href: "/", key: "nav.dashboard" },
      { href: "/review", key: "nav.review", badge: true },
    ],
  },
  {
    key: "nav.money",
    items: [
      { href: "/transactions", key: "nav.transactions" },
      { href: "/statement", key: "nav.statement" },
      { href: "/insights", key: "nav.insights" },
    ],
  },
  {
    key: "nav.system",
    items: [{ href: "/settings", key: "nav.settings" }],
  },
];

function RunTicker() {
  const { run } = useApp();
  if (!run || !["starting", "fetching", "parsing"].includes(run.status)) return null;
  const pct = run.total ? Math.round((run.done / run.total) * 100) : 0;
  return (
    <div className="mt-3">
      <div className="num flex items-center justify-between text-[0.76rem] text-ink-3">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-soft" />
          {run.status === "fetching" ? "Reading inbox" : "Parsing"}
        </span>
        {run.total ? (
          <span>
            {run.done}/{run.total}
          </span>
        ) : null}
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--hover-strong)]">
        <div className="bar h-full rounded-full transition-[width]" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Rail({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { t } = useT();
  const { session, stats, startSync, startDemo, run } = useApp();
  const syncing = Boolean(run && ["starting", "fetching", "parsing"].includes(run.status));

  return (
    <div className="flex h-full flex-col justify-between">
      <div>
        <Link href="/" onClick={onNavigate} className="flex h-[68px] items-center px-5">
          <Lockup size={30} />
        </Link>

        <div className="px-4 py-5">
          {session?.gmail_connected ? (
            <button onClick={startSync} disabled={syncing} className="btn-primary w-full disabled:opacity-45">
              {syncing ? "Syncing…" : "Sync inbox"}
            </button>
          ) : (
            <button onClick={startDemo} disabled={syncing} className="btn w-full">
              {t("nav.runSample")}
            </button>
          )}
          <RunTicker />
        </div>

        <nav className="px-3">
          {SECTIONS.map((section) => (
            <div key={section.key} className="mb-5">
              <div className="eyebrow px-3 pb-2">{t(section.key)}</div>
              <div className="space-y-1">
                {section.items.map((item) => {
                  const active = pathname === item.href;
                  const count = item.badge ? stats?.needs_review ?? 0 : 0;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onNavigate}
                      className={`flex h-11 items-center justify-between rounded-[12px] px-3 text-[0.92rem] transition-colors ${
                        active
                          ? "border border-[rgba(96,165,250,0.28)] bg-[rgba(59,130,246,0.14)] font-semibold text-ink shadow-[inset_0_1px_0_var(--hairline)]"
                          : "border border-transparent text-ink-3 hover:bg-[var(--hover)] hover:text-ink"
                      }`}
                    >
                      {t(item.key)}
                      {count > 0 ? (
                        <span className="num rounded-full bg-[rgba(251,191,36,0.16)] px-2 py-0.5 text-[0.72rem] font-semibold text-amber">
                          {count > 99 ? "99+" : count}
                        </span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div className="border-t border-line px-5 py-5">
        <div className="num text-[0.74rem] text-ink-4">
          {session?.storage ?? "local"}
          {session?.linked_legacy_accounts ? ` · +${session.linked_legacy_accounts} linked` : ""}
        </div>
      </div>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <div className="relative z-10 flex min-h-screen">
      <aside className="hidden w-[248px] shrink-0 border-r border-line bg-[var(--chrome-soft)] backdrop-blur-sm lg:block">
        <div className="sticky top-0 h-screen overflow-y-auto">
          <Rail />
        </div>
      </aside>

      {/* Small screens get the same rail as a drawer rather than a strip of
          tabs across the top. */}
      {open ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-[var(--scrim)]" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-[268px] overflow-y-auto border-r border-line bg-[var(--chrome)] shadow-[0_20px_60px_rgba(2,6,23,0.55)]">
            <Rail onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMenu={() => setOpen(true)} />
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-8 lg:px-10">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-7">
      <h1 className="font-[family-name:var(--font-display)] text-[1.6rem] font-bold tracking-[-0.025em] text-ink">
        {title}
      </h1>
      {description ? <p className="mt-2 max-w-2xl text-[0.95rem] text-ink-3">{description}</p> : null}
    </div>
  );
}

/** Filters and actions on one line, above the grid they act on. */
export function Toolbar({ children }: { children: React.ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-center gap-3">{children}</div>;
}
