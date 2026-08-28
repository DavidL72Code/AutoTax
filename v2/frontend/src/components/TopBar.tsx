"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/AppState";
import { useT } from "@/lib/i18n";
import { Mark } from "@/components/Brand";
import { Pill } from "@/components/ui";
import { money } from "@/lib/format";

/* A utility bar, not a navigation bar — it carries the two things that follow
   you around the app rather than a copy of the sidebar. */

function useDismissable<T extends HTMLElement>(onClose: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [onClose]);
  return ref;
}

function BellIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

const TONE: Record<string, string> = { alert: "bad", warning: "review", info: "accent" };

function NotificationBell() {
  const { session, notifications, unreadNotifications, refreshNotifications, markNotificationsRead, connectGmail } =
    useApp();
  const [open, setOpen] = useState(false);
  const ref = useDismissable<HTMLDivElement>(() => setOpen(false));
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);

  const signedIn = Boolean(session?.signed_in);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && signedIn) void refreshNotifications();
  };

  const recent = (notifications?.items ?? []).slice(0, 6);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        aria-label={`Notifications${unreadNotifications ? `, ${unreadNotifications} unread` : ""}`}
        className={`relative grid h-11 w-11 place-items-center rounded-[12px] border transition-colors ${
          open
            ? "border-[rgba(96,165,250,0.35)] bg-[rgba(59,130,246,0.14)] text-ink"
            : "border-line-strong bg-[var(--dot-soft)] text-ink-3 hover:border-[var(--dot)] hover:text-ink"
        }`}
      >
        <BellIcon />
        {unreadNotifications ? (
          <span className="num absolute -top-1.5 -right-1.5 min-w-[20px] rounded-full border border-[var(--chrome)] bg-[#dc2626] px-1 text-[0.66rem] leading-[18px] font-semibold text-white">
            {unreadNotifications > 9 ? "9+" : unreadNotifications}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="panel panel-sm absolute right-0 z-50 mt-2 w-[380px] max-w-[calc(100vw-2rem)]">
          <div className="flex items-center justify-between border-b border-[var(--hairline)] px-4 py-3">
            <span className="eyebrow">Notifications</span>
            {unreadNotifications ? (
              <button
                onClick={() => markNotificationsRead({ all: true })}
                className="text-[0.8rem] text-ink-4 transition-colors hover:text-ink-2"
              >
                Mark all read
              </button>
            ) : null}
          </div>

          {!signedIn ? (
            <div className="px-4 py-7 text-center">
              <p className="text-[0.85rem] text-ink-3">Sign in to get notifications</p>
              <p className="mt-1.5 text-[0.8rem] leading-relaxed text-ink-4">
                Duplicate charges, subscription price rises and bills about to land.
              </p>
              <button onClick={connectGmail} className="btn-primary mt-4">
                Sign in with Google
              </button>
            </div>
          ) : recent.length ? (
            <ul className="max-h-[380px] overflow-y-auto">
              {recent.map((item) => (
                <li key={item.id} className={item.read ? "opacity-55" : ""}>
                  <Link
                    href={item.href}
                    onClick={() => {
                      if (!item.read) void markNotificationsRead({ ids: [item.id] });
                      setOpen(false);
                    }}
                    className="flex gap-3 border-b border-[var(--hairline)] px-4 py-3 transition-colors last:border-0 hover:bg-[var(--wash)]"
                  >
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        item.read ? "bg-[var(--dot)]" : "bg-accent"
                      }`}
                    />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <Pill tone={TONE[item.severity] ?? "accent"}>{item.severity}</Pill>
                        <span className="text-[0.88rem] font-medium text-ink">{item.title}</span>
                      </span>
                      <span className="mt-1 block text-[0.8rem] leading-relaxed text-ink-4">
                        {item.body.length > 110 ? `${item.body.slice(0, 110)}…` : item.body}
                      </span>
                      {item.amount !== null ? (
                        <span className="num mt-1 block text-[0.8rem] text-ink-3">{money(item.amount)}</span>
                      ) : null}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-8 text-center text-[0.85rem] text-ink-4">
              All quiet. Duplicate charges, price rises and upcoming bills land here.
            </p>
          )}

          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-[var(--hairline)] px-4 py-3 text-center text-[0.85rem] text-accent-soft hover:underline"
          >
            See all notifications
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function AccountMenu() {
  const { session, signOut } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useDismissable<HTMLDivElement>(() => setOpen(false));

  const email = session?.email ?? "";
  const initial = email.trim().charAt(0).toUpperCase() || "?";

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={`flex h-11 items-center gap-2.5 rounded-[12px] border px-2.5 transition-colors ${
          open
            ? "border-[rgba(96,165,250,0.35)] bg-[rgba(59,130,246,0.14)]"
            : "border-line-strong bg-[var(--dot-soft)] hover:border-[var(--dot)]"
        }`}
      >
        <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-b from-[#60a5fa] to-[#2563eb] text-[0.78rem] font-bold text-white">
          {initial}
        </span>
        <span className="hidden max-w-[168px] truncate text-[0.85rem] text-ink-2 sm:block">{email}</span>
      </button>

      {open ? (
        <div className="panel panel-sm absolute right-0 z-50 mt-2 w-[240px]">
          <div className="border-b border-[var(--hairline)] px-4 py-3">
            <div className="truncate text-[0.85rem] text-ink">{email}</div>
            <div className="num mt-1 text-[0.74rem] text-ink-4">
              {session?.gmail_connected ? "Gmail connected" : "Gmail not connected"} · {session?.storage}
            </div>
          </div>
          <Link
            href="/settings"
            onClick={() => setOpen(false)}
            className="block px-4 py-3 text-[0.88rem] text-ink-2 transition-colors hover:bg-[var(--wash)] hover:text-ink"
          >
            Settings
          </Link>
          <button
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
            className="block w-full px-4 py-3 text-left text-[0.88rem] text-ink-3 transition-colors hover:bg-[var(--wash)] hover:text-ink"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { session, connectGmail } = useApp();
  const { t } = useT();

  return (
    <header className="sticky top-0 z-40 flex h-[68px] shrink-0 items-center gap-3 border-b border-line bg-[var(--chrome-veil)] px-5 backdrop-blur-md lg:px-8">
      <button
        onClick={onOpenMenu}
        aria-label={t("nav.openMenu")}
        className="btn-ghost h-10 w-10 justify-center px-0 lg:hidden"
      >
        <span className="flex flex-col gap-[3px]">
          <span className="block h-px w-4 bg-current" />
          <span className="block h-px w-4 bg-current" />
          <span className="block h-px w-4 bg-current" />
        </span>
      </button>
      <Link href="/" className="lg:hidden" aria-label={t("nav.home")}>
        <Mark size={26} />
      </Link>

      <div className="ml-auto flex items-center gap-3">
        {/* Always rendered. A control that vanishes when signed out — or when
            the API is unreachable and `session` is still null — reads as a
            missing feature rather than an empty one. */}
        <NotificationBell />
        {session?.signed_in ? (
          <AccountMenu />
        ) : (
          /* Signing in *is* connecting Gmail — one Google grant, no second
             account to create. */
          <button onClick={connectGmail} className="btn-primary">
            Sign in with Google
          </button>
        )}
      </div>
    </header>
  );
}
