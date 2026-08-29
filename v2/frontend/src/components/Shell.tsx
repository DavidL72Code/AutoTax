"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
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
      { href: "/", key: "nav.home2" },
      { href: "/dashboard", key: "nav.dashboard" },
      { href: "/review", key: "nav.review", badge: true },
    ],
  },
  {
    key: "nav.money",
    items: [
      { href: "/transactions", key: "nav.transactions" },
      { href: "/statement", key: "nav.statement" },
      { href: "/insights", key: "nav.insights" },
      { href: "/advisor", key: "nav.advisor" },
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
  const router = useRouter();
  const syncing = Boolean(run && ["starting", "fetching", "parsing"].includes(run.status));

  return (
    <div className="flex h-full flex-col justify-between">
      <div>
        <div className="px-4 pb-5 pt-6">
          {session?.gmail_connected ? (
            <button onClick={startSync} disabled={syncing} className="btn-primary w-full disabled:opacity-45">
              {syncing ? "Syncing…" : "Sync inbox"}
            </button>
          ) : (
            <button
              onClick={() => void startDemo().then(() => router.push("/dashboard"))}
              disabled={syncing}
              className="btn w-full"
            >
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

const RAIL_KEY = "receiptauto:rail";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  /* The rail used to be pinned open above `lg` with the toggle hidden, so the
     button did nothing on the screens most people use it on. It is a real
     toggle now, on every width, and the choice is remembered. */
  const [open, setOpen] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(RAIL_KEY);
    setOpen(stored === null ? window.innerWidth >= 1024 : stored === "open");
  }, []);

  const toggle = () => {
    setOpen((current) => {
      localStorage.setItem(RAIL_KEY, current ? "closed" : "open");
      return !current;
    });
  };

  // On a narrow screen the rail covers the page, so following a link should
  // close it. On a wide one it sits beside the page and should stay put.
  useEffect(() => {
    if (window.innerWidth < 1024) setOpen(false);
  }, [pathname]);

  return (
    <div className="relative z-10 min-h-screen">
      <TopBar onOpenMenu={toggle} railOpen={open} />

      <div className="flex">
        {open ? (
          <div
            className="fixed inset-0 z-40 bg-[var(--scrim)] lg:hidden"
            onClick={() => setOpen(false)}
            aria-hidden
          />
        ) : null}

        <aside
          className={`${
            open ? "translate-x-0" : "-translate-x-full"
          } fixed inset-y-0 left-0 z-40 w-[248px] shrink-0 overflow-y-auto border-r border-line bg-[var(--chrome-soft)] pt-[68px] backdrop-blur-sm transition-transform duration-200 lg:sticky lg:top-[68px] lg:z-0 lg:h-[calc(100vh-68px)] lg:pt-0 ${
            open ? "lg:block" : "lg:hidden"
          }`}
        >
          <Rail onNavigate={() => window.innerWidth < 1024 && setOpen(false)} />
        </aside>

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
