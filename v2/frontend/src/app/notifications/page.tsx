"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { useT } from "@/lib/i18n";
import { PageHeader, Toolbar } from "@/components/Shell";
import { Button, Empty, Panel, Pill } from "@/components/ui";
import { money } from "@/lib/format";

const TONE: Record<string, { pill: string; key: string }> = {
  alert: { pill: "bad", key: "notifications.toneAlert" },
  warning: { pill: "review", key: "notifications.toneWarning" },
  info: { pill: "accent", key: "notifications.toneInfo" },
};

/** Relative time in the reader's language. `t` is passed in rather than hooked
    because this is a plain function called during render. */
function relative(at: string, t: (key: string, params?: Record<string, unknown>) => string): string {
  const then = new Date(at).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return t("time.justNow");
  if (minutes < 60) return t("time.minutes", { n: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return t("time.hours", { n: hours });
  return t("time.days", { n: Math.round(hours / 24) });
}

export default function NotificationsPage() {
  const { notifications, refreshNotifications, markNotificationsRead, session } = useApp();
  const { t } = useT();
  const [unreadOnly, setUnreadOnly] = useState(false);

  useEffect(() => {
    void refreshNotifications();
  }, [refreshNotifications]);

  if (!session?.signed_in) {
    return (
      <>
        <PageHeader title={t("notifications.title")} />
        <Panel flush>
          <Empty title={t("notifications.signIn")}>
            Duplicate charges, subscription price rises, bills about to land and receipts waiting on you all
            show up here.
          </Empty>
        </Panel>
      </>
    );
  }

  if (!notifications) return <p className="text-[0.9rem] text-ink-3">{t("common.loading")}</p>;

  const items = unreadOnly ? notifications.items.filter((item) => !item.read) : notifications.items;

  return (
    <>
      <PageHeader
        title={t("notifications.title")}
        description={t("notifications.headerDescription")}
      />

      <Toolbar>
        <span className="text-[0.9rem] text-ink-3">
          <span className="num text-ink">{notifications.unread}</span> {t("notifications.unreadOf", { total: notifications.items.length })}
        </span>
        <Button variant="ghost" onClick={() => setUnreadOnly(!unreadOnly)}>
          {unreadOnly ? t("common.showAll") : t("notifications.unreadOnly")}
        </Button>
        <span className="ml-auto" />
        <Button onClick={() => markNotificationsRead({ all: true })} disabled={!notifications.unread}>
          {t("notifications.markAllRead")}
        </Button>
      </Toolbar>

      <Panel flush>
        {items.length ? (
          <ul>
            {items.map((item) => {
              const tone = TONE[item.severity] ?? TONE.info;
              return (
                <li
                  key={item.id}
                  className={`flex gap-4 border-b border-[var(--hairline)] px-6 py-5 last:border-0 ${
                    item.read ? "opacity-55" : ""
                  }`}
                >
                  <span
                    className={`mt-2 h-2 w-2 shrink-0 rounded-full ${
                      item.read
                        ? "bg-[var(--dot)]"
                        : "bg-accent shadow-[0_0_0_3px_rgba(59,130,246,0.18)]"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <Pill tone={tone.pill}>{t(tone.key)}</Pill>
                      <span className="font-medium text-ink">{item.title}</span>
                      {item.amount !== null ? (
                        <span className="num text-ink-2">{money(item.amount)}</span>
                      ) : null}
                    </div>
                    <p className="mt-1.5 text-[0.88rem] leading-relaxed text-ink-3">{item.body}</p>
                    <div className="mt-3 flex items-center gap-4">
                      <Link href={item.href} className="text-[0.85rem] text-accent-soft hover:underline">
                        {t("notifications.open")}
                      </Link>
                      {!item.read ? (
                        <button
                          onClick={() => markNotificationsRead({ ids: [item.id] })}
                          className="text-[0.85rem] text-ink-4 transition-colors hover:text-ink-2"
                        >
                          {t("notifications.markRead")}
                        </button>
                      ) : null}
                      <span className="num ml-auto text-[0.76rem] text-ink-4">{relative(item.at, t)}</span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <Empty title={t(unreadOnly ? "notifications.nothingUnread" : "notifications.allQuiet")}>
            Duplicate charges, subscription price rises, bills about to land and receipts waiting on you all
            show up here.
          </Empty>
        )}
      </Panel>
    </>
  );
}
