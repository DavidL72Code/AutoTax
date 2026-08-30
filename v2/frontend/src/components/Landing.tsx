"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApp } from "@/components/AppState";
import { GraphDiagram } from "@/components/GraphDiagram";
import { Button, Panel } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* The home page, in the shape v1's `index.html` had: a badge, a two-line
   headline with the second line accented, a sub, the calls to action, a trust
   row, then the product itself, then how it works.

   One deliberate difference. v1 showed a mocked dashboard, invented merchants
   and invented totals, as the preview. This shows the real graph instead. It
   is the honest version of the same idea, and it is also the actual claim the
   app makes: that every figure carries the steps that produced it. */
export function Landing() {
  const { connectGmail, startDemo, session, stats } = useApp();
  const { t } = useT();
  const router = useRouter();

  const hasLedger = Boolean(session?.signed_in && stats?.receipt_count);

  // The run streams into the dashboard, so starting it from here should take
  // you there, otherwise the sample appears to do nothing.
  const runSample = async () => {
    await startDemo();
    router.push("/dashboard");
  };

  const steps = [
    { title: t("home.step1"), body: t("home.step1Body") },
    { title: t("home.step2"), body: t("home.step2Body") },
    { title: t("home.step3"), body: t("home.step3Body") },
  ];

  return (
    <>
      <section className="pb-2 pt-6 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-[var(--hairline-strong)] bg-[var(--wash)] px-3.5 py-1.5 text-[0.78rem] text-ink-3">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          {t("home.badge")}
        </span>

        <h1 className="mx-auto mt-6 max-w-4xl font-[family-name:var(--font-display)] text-[2.4rem] font-bold leading-[1.08] tracking-[-0.03em] text-ink sm:text-[3.4rem]">
          {t("home.titleA")}
          <br />
          <span className="text-accent">{t("home.titleB")}</span>
        </h1>

        <p className="mx-auto mt-5 max-w-2xl text-[1.02rem] leading-relaxed text-ink-3">{t("home.lede")}</p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {hasLedger ? (
            <>
              <Link href="/dashboard" className="btn-primary">
                {t("home.openLedger")} →
              </Link>
              <Link href="/insights" className="btn">
                {t("nav.insights")}
              </Link>
            </>
          ) : (
            <>
              <Button variant="primary" onClick={connectGmail}>
                {t("home.getStarted")} →
              </Button>
              <Button onClick={() => void runSample()}>{t("home.viewDemo")}</Button>
            </>
          )}
          <a href="#how" className="btn-ghost">
            {t("home.howItWorks")}
          </a>
        </div>

        <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[0.82rem] text-ink-4">
          {["home.trust1", "home.trust2", "home.trust3", "home.trust4"].map((key) => (
            <li key={key} className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-[var(--dot)]" />
              {t(key)}
            </li>
          ))}
        </ul>
      </section>

      <Panel title={t("home.graphTitle")} flush className="mt-10" id="how">
        <div className="px-6 pt-4">
          <p className="max-w-3xl text-[0.9rem] leading-relaxed text-ink-3">{t("home.graphSub")}</p>
        </div>
        {/* Capped: the SVG scales to its container, and a full-width panel blows
            the nodes up to poster size. */}
        <div className="mx-auto w-full max-w-[560px]">
          <GraphDiagram records={[]} active={false} />
        </div>
      </Panel>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {steps.map((step, index) => (
          <Panel key={step.title}>
            <div className="py-1">
              <div className="num text-[0.76rem] uppercase tracking-[0.14em] text-ink-4">
                {t("home.step", { n: String(index + 1).padStart(2, "0") })}
              </div>
              <h3 className="mt-2 font-[family-name:var(--font-display)] text-[1.05rem] font-bold text-ink">
                {step.title}
              </h3>
              <p className="mt-2 text-[0.88rem] leading-relaxed text-ink-3">{step.body}</p>
            </div>
          </Panel>
        ))}
      </div>

      {!hasLedger ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
      ) : null}

      {session && !session.model_configured ? (
        <p className="mt-4 text-[0.85rem] text-amber">{t("settings.assistedOff")}</p>
      ) : null}
    </>
  );
}
