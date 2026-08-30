"use client";

import { useApp } from "@/components/AppState";
import { PageHeader } from "@/components/Shell";
import { Button, Empty, Panel } from "@/components/ui";
import { useTheme } from "@/components/Theme";
import { LOCALES, useT } from "@/lib/i18n";
import { API_BASE } from "@/lib/api";

function Row({ label, value, action }: { label: string; value: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--hairline)] px-6 py-5 last:border-0">
      <div className="min-w-0">
        <div className="font-medium text-ink">{label}</div>
        <div className="mt-1 text-[0.85rem] text-ink-3">{value}</div>
      </div>
      {action}
    </div>
  );
}

export default function SettingsPage() {
  const { session, connectGmail, signOut, loading } = useApp();
  const { choice, setChoice } = useTheme();
  const { locale, setLocale, t } = useT();

  if (loading) {
    return (
      <Panel flush>
        <Empty title={t("common.loading")} />
      </Panel>
    );
  }

  return (
    <>
      <PageHeader title={t("settings.title")} description={t("settings.description")} />

      <Panel title={t("settings.account")} flush className="mb-4">
        <Row
          label={t("settings.gmail")}
          value={
            session?.gmail_connected
              ? t("settings.gmailConnected", { email: session.email })
              : t("settings.gmailNotConnected")
          }
          action={
            session?.gmail_connected ? (
              <Button onClick={signOut}>{t("nav.signOut")}</Button>
            ) : (
              <Button variant="primary" onClick={connectGmail}>
                {t("nav.signIn")}
              </Button>
            )
          }
        />
        <Row
          label={t("settings.assistedParsing")}
          value={
            session?.model_configured
              ? t("settings.assistedOn")
              : t("settings.assistedOff")
          }
        />
      </Panel>

      <Panel title={t("settings.appearance")} flush className="mb-4">
        <Row
          label={t("settings.theme")}
          value={
            choice === "system"
              ? t("settings.followingSystem")
              : choice === "light"
                ? t("settings.themeLight")
                : t("settings.themeDark")
          }
          action={
            <div className="flex gap-1.5">
              {(["dark", "light", "system"] as const).map((option) => (
                <Button
                  key={option}
                  variant={choice === option ? "primary" : undefined}
                  onClick={() => setChoice(option)}
                >
                  {t(option === "system" ? "settings.themeSystem" : option === "dark" ? "settings.themeDark" : "settings.themeLight")}
                </Button>
              ))}
            </div>
          }
        />
        <Row
          label={t("settings.language")}
          value={t("settings.languageSub")}
          action={
            <select
              className="field"
              value={locale}
              onChange={(event) => setLocale(event.target.value)}
              aria-label={t("settings.language")}
            >
              {Object.entries(LOCALES).map(([code, meta]) => (
                <option key={code} value={code}>
                  {meta.name}
                </option>
              ))}
            </select>
          }
        />
      </Panel>

      <Panel title={t("settings.dataHandling")} className="mb-4">
        <div className="max-w-2xl space-y-3 text-[0.92rem] leading-relaxed text-ink-2">
          <p>{t("settings.data1")}</p>
          <p>{t("settings.data2")}</p>
          <p>{t("settings.data3")}</p>
          <p>{t("settings.data4")}</p>
        </div>
      </Panel>

      {/* Not settings, nothing here is a choice. It is what the server is
          currently wired to, kept because it is the first thing worth reading
          when something is not working. */}
      <details className="panel px-6 py-4">
        <summary className="cursor-pointer select-none text-[0.9rem] text-ink-3 hover:text-ink">
          {t("settings.diagnostics")}
        </summary>
        <div className="mt-4 space-y-2 text-[0.85rem]">
          <div className="flex justify-between gap-4">
            <span className="text-ink-3">{t("settings.storage")}</span>
            <span className="num text-ink-2">
              {session?.storage}
              {session?.linked_legacy_accounts
                ? ` · ${session.linked_legacy_accounts} linked v1 account(s)`
                : ""}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-ink-3">{t("settings.api")}</span>
            <span className="num text-ink-2">{API_BASE}</span>
          </div>
        </div>
      </details>
    </>
  );
}
