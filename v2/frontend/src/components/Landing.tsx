"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApp } from "@/components/AppState";
import { GraphDiagram } from "@/components/GraphDiagram";
import { Button, Panel } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* The signed-out home. Someone who has not connected anything still deserves to
   see what the thing does — so the graph is here, unpopulated, next to the two
   ways in. The demo is the honest one to lead with: it runs the real pipeline,
   costs nothing, and asks for no access. */
export function Landing() {
  const { connectGmail, startDemo, session, stats } = useApp();
  const { t } = useT();
  // Home is now a real destination rather than a fallback, so someone who
  // already has a ledger must be able to get to it from here.
  const hasLedger = Boolean(session?.signed_in && stats?.receipt_count);
  const router = useRouter();
  // The run streams into the dashboard, so starting it from here should take
  // you there — otherwise the sample appears to do nothing.
  const runSample = async () => {
    await startDemo();
    router.push("/dashboard");
  };

  return (
    <>
      <section className="mb-5">
        <h1 className="max-w-3xl font-[family-name:var(--font-display)] text-[2rem] font-bold leading-[1.15] tracking-[-0.025em] text-ink sm:text-[2.4rem]">
          {t("home.tagline")}
        </h1>
        <p className="mt-4 max-w-2xl text-[1rem] leading-relaxed text-ink-3">{t("home.lede")}</p>
      </section>

      {hasLedger ? (
        <Panel className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4 py-1">
            <div>
              <h2 className="font-[family-name:var(--font-display)] text-[1.15rem] font-bold text-ink">
                {t("home.goToDashboard")}
              </h2>
              <p className="mt-1 text-[0.9rem] text-ink-3">
                {t("home.goToDashboardSub", { count: stats?.receipt_count ?? 0 })}
              </p>
            </div>
            <Link href="/dashboard" className="btn-primary">
              {t("nav.dashboard")}
            </Link>
          </div>
        </Panel>
      ) : null}

      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <Panel>
          <div className="py-1">
            <h2 className="font-[family-name:var(--font-display)] text-[1.15rem] font-bold text-ink">
              {t("home.tryIt")}
            </h2>
            <p className="mt-2 text-[0.9rem] leading-relaxed text-ink-3">{t("home.tryItSub")}</p>
            <div className="mt-4">
              <Button variant="primary" onClick={() => void runSample()}>
                {t("nav.runSample")}
              </Button>
            </div>
          </div>
        </Panel>

        <Panel>
          <div className="py-1">
            <h2 className="font-[family-name:var(--font-display)] text-[1.15rem] font-bold text-ink">
              {t("home.orConnect")}
            </h2>
            <p className="mt-2 text-[0.9rem] leading-relaxed text-ink-3">{t("home.orConnectSub")}</p>
            <div className="mt-4">
              <Button onClick={connectGmail}>{t("nav.signIn")}</Button>
            </div>
          </div>
        </Panel>
      </div>

      <Panel title={t("home.graphTitle")} flush>
        <div className="px-6 pt-4">
          <p className="max-w-3xl text-[0.9rem] leading-relaxed text-ink-3">{t("home.graphSub")}</p>
        </div>
        {/* No records yet, so it renders as the shape of the pipeline rather
            than as live traffic — which is exactly what a first visit wants.
            Capped, because the SVG scales to its container and a full-width
            panel blows the nodes up to poster size. */}
        <div className="mx-auto w-full max-w-[560px]">
          <GraphDiagram records={[]} active={false} />
        </div>
      </Panel>

      {session && !session.model_configured ? (
        <p className="mt-4 text-[0.85rem] text-amber">{t("settings.assistedOff")}</p>
      ) : null}
    </>
  );
}

