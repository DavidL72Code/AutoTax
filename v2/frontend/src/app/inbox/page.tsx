"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { Empty, Panel } from "@/components/ui";
import { SampleEmail, SampleEnvelope, Transaction, api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useT } from "@/lib/i18n";

/* A real receipt links out to Gmail, which holds the authoritative copy. A
   generated one has nowhere to link to, so a demo visitor could see figures
   without ever being able to check one. This is the missing half of the claim
   that every number is traceable. */
export default function InboxPage() {
  const { t } = useT();
  const { session, transactions } = useApp();
  const [items, setItems] = useState<SampleEnvelope[] | null>(null);
  const [open, setOpen] = useState<SampleEmail | null>(null);
  const [highlighted, setHighlighted] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await api.sampleInbox()).items);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => {
    if (session?.is_demo) void load();
    else setItems([]);
  }, [session?.is_demo, load]);

  const show = useCallback(async (emailId: string) => {
    try {
      setOpen(await api.sampleEmail(emailId));
      setHighlighted(emailId);
    } catch {
      // The run it belonged to is gone; the list is still worth showing.
    }
  }, []);

  /* Arriving from a figure means arriving *at* its email. Linking to the page
     and leaving someone to find the row themselves is the same as not linking:
     the whole point is to check one number without hunting for it. */
  useEffect(() => {
    if (!items?.length) return;
    const jump = () => {
      const wanted = decodeURIComponent(window.location.hash.replace("#", ""));
      if (!wanted) return;
      void show(wanted);
      // The row stays marked behind the dialog, so closing it leaves you where
      // you were rather than at the top of the list.
      document.getElementById(`email-${wanted}`)?.scrollIntoView({ block: "center" });
    };
    jump();
    window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, [items, show]);

  // What the pipeline made of each email, looked up by the id it was parsed
  // under, so the two can be read side by side.
  const parsed = new Map<string, Transaction>();
  for (const row of transactions) {
    if (row.email_id) parsed.set(row.email_id, row);
  }

  return (
    <>
      <PageHeader title={t("inbox.title")} description={t("inbox.description")} />

      {!items?.length ? (
        <Panel flush>
          <Empty title={t("inbox.empty")}>{t("inbox.emptyBody")}</Empty>
        </Panel>
      ) : (
        <Panel title={t("inbox.count", { count: items.length })} flush>
          <ul>
            {items.map((item) => {
              const record = item.id ? parsed.get(item.id) : undefined;
              return (
                <li
                  key={item.id}
                  id={`email-${item.id}`}
                  className={`border-b border-[var(--hairline)] last:border-0 ${
                    highlighted === item.id ? "bg-[rgba(59,130,246,0.10)]" : ""
                  }`}
                >
                  <button
                    onClick={() => void show(item.id)}
                    className="block w-full px-6 py-4 text-left transition-colors hover:bg-[var(--wash)]"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <span className="font-medium text-ink">{item.subject}</span>
                      <span className="num text-[0.8rem] text-ink-4">{shortDate(item.date)}</span>
                    </div>
                    <div className="num mt-1 text-[0.8rem] text-ink-4">{item.sender}</div>
                    <p className="mt-2 line-clamp-1 text-[0.84rem] text-ink-3">{item.preview}</p>
                    <div className="mt-2 text-[0.82rem]">
                      {record ? (
                        <span className="text-ink-3">
                          {t("inbox.parsedAs")}{" "}
                          <span className="font-medium text-ink">{record.vendor}</span>{" "}
                          <span className="num text-ink">{money(record.amount)}</span>
                        </span>
                      ) : (
                        <span className="text-ink-4">{t("inbox.notParsed")}</span>
                      )}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}

      {open ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[var(--scrim)] p-6">
          <div className="panel w-full max-w-[760px]">
            <header className="panel-head">
              <h2 className="panel-title">{open.subject}</h2>
              <button onClick={() => setOpen(null)} className="text-[0.85rem] text-ink-4 hover:text-ink">
                {t("inbox.close")}
              </button>
            </header>
            <div className="px-6 py-5">
              <div className="num mb-3 text-[0.8rem] text-ink-4">
                {open.sender} · {shortDate(open.date)}
              </div>
              {/* Fixture text the server wrote, but rendered as text all the
                  same: nothing from an email body is ever treated as markup. */}
              <pre className="num max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-[10px] border border-[var(--hairline)] bg-[var(--wash)] p-4 text-[0.8rem] leading-[1.6] text-ink-2">
                {open.body}
              </pre>
              <p className="mt-3 text-[0.78rem] text-ink-4">{t("inbox.generated")}</p>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
