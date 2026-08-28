"use client";

import { useRef, useState } from "react";
import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { Button, Empty, Panel, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Turn = { role: "user" | "assistant"; content: string };

/* The model is asked to open with a disclaimer, and it does — but a guardrail
   that depends on the model remembering is not a guardrail. This one is part of
   the page, above the conversation, always. */
function Disclaimer() {
  const { t } = useT();
  return (
    <p className="mb-4 rounded-[10px] border border-[var(--hairline-strong)] bg-[var(--wash)] px-4 py-3 text-[0.82rem] leading-relaxed text-ink-3">
      {t("advisor.disclaimer")}
    </p>
  );
}

/* The model is told to use *word* for emphasis and - for bullets, so that this
   can render without a markdown dependency — and so nothing it returns is ever
   interpreted as HTML. */
function Reply({ text }: { text: string }) {
  return (
    <div className="space-y-1.5">
      {text.split("\n").map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return null;
        const bullet = trimmed.startsWith("- ");
        const body = bullet ? trimmed.slice(2) : trimmed;
        const parts = body.split(/\*([^*]+)\*/g);
        return (
          <p
            key={index}
            className={`text-[0.9rem] leading-relaxed text-ink-2 ${bullet ? "pl-4 -indent-3" : ""}`}
          >
            {bullet ? "· " : ""}
            {parts.map((part, i) =>
              i % 2 === 1 ? (
                <strong key={i} className="font-medium text-ink">
                  {part}
                </strong>
              ) : (
                part
              ),
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function AdvisorPage() {
  const { t } = useT();
  const { session, stats } = useApp();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [considered, setConsidered] = useState<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const ready = Boolean(session?.signed_in && stats?.receipt_count);

  const ask = async (question: string) => {
    const message = question.trim();
    if (!message || busy) return;
    setError(null);
    setBusy(true);
    setDraft("");
    // The asked turn goes up immediately; history sent is what came before it.
    const history = turns;
    setTurns([...turns, { role: "user", content: message }]);
    try {
      const answer = await api.advisorAsk(message, history);
      setTurns((current) => [...current, { role: "assistant", content: answer.reply }]);
      setConsidered(answer.receipts_considered);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("advisor.failed"));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior: "smooth" }));
    }
  };

  return (
    <>
      <PageHeader title={t("advisor.title")} description={t("advisor.description")} />
      <Disclaimer />

      <Panel flush>
        {!ready ? (
          <Empty title={t("advisor.empty")}>{t("advisor.signedOut")}</Empty>
        ) : turns.length === 0 ? (
          <div className="px-6 py-8">
            <div className="mb-1 font-medium text-ink">{t("advisor.empty")}</div>
            <p className="mb-4 max-w-xl text-[0.88rem] leading-relaxed text-ink-3">
              {t("advisor.emptyBody")}
            </p>
            <div className="flex flex-wrap gap-2">
              {["advisor.s1", "advisor.s2", "advisor.s3"].map((key) => (
                <Button key={key} onClick={() => ask(t(key))}>
                  {t(key)}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="max-h-[540px] space-y-0 overflow-y-auto">
            {turns.map((turn, index) => (
              <li
                key={index}
                className="border-b border-[var(--hairline)] px-6 py-4 last:border-0"
              >
                <div className="eyebrow mb-2">
                  {turn.role === "user" ? t("advisor.you") : t("advisor.ra")}
                </div>
                {turn.role === "user" ? (
                  <p className="text-[0.9rem] text-ink">{turn.content}</p>
                ) : (
                  <Reply text={turn.content} />
                )}
              </li>
            ))}
            {busy ? (
              <li className="px-6 py-4 text-[0.88rem] text-ink-4">{t("advisor.thinking")}</li>
            ) : null}
            <div ref={bottom} />
          </ul>
        )}
      </Panel>

      {error ? <p className="mt-3 text-[0.85rem] text-down">{error}</p> : null}

      {ready ? (
        <form
          className="mt-4 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void ask(draft);
          }}
        >
          <input
            className={`${inputClass} flex-1 min-w-[260px]`}
            placeholder={t("advisor.placeholder")}
            value={draft}
            maxLength={2000}
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button variant="primary" type="submit" disabled={busy || !draft.trim()}>
            {t("advisor.send")}
          </Button>
          {considered !== null ? (
            <span className="num self-center text-[0.8rem] text-ink-4">
              {t("advisor.considered", { count: considered })}
            </span>
          ) : null}
        </form>
      ) : null}
    </>
  );
}
