import Link from "next/link";
import { ReactNode } from "react";

/* Primitives carry the geometry and the polish, so no page has to hand-roll a
   padding value. Every size here comes from v1's stylesheet. */

export function Panel({
  title,
  action,
  children,
  className = "",
  flush = false,
  id,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Skip the inner padding when the child is a full-bleed table. */
  flush?: boolean;
  /** For in-page anchors, e.g. a "how it works" link on the home page. */
  id?: string;
}) {
  return (
    <section id={id} className={`panel ${className}`}>
      {(title || action) && (
        <header className="panel-head">
          <h2 className="panel-title">{title}</h2>
          {action}
        </header>
      )}
      <div className={flush ? "" : "px-6 py-5"}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "up" | "down" | "accent";
}) {
  const tones = {
    neutral: "text-ink",
    up: "text-up",
    down: "text-down",
    accent: "text-amber",
  };
  return (
    <div className="panel panel-sm px-6 py-5">
      <div className="eyebrow">{label}</div>
      <div className={`figure mt-3 ${tones[tone]}`}>{value}</div>
      {sub ? <div className="mt-2.5 text-[0.85rem] text-ink-3">{sub}</div> : null}
    </div>
  );
}

/** Signed money. Direction is carried by the arrow as well as the colour, so
    it survives a colourblind reader and a black-and-white print. */
export function Delta({ value, format }: { value: number; format: (n: number) => string }) {
  if (!value) return <span className="num text-ink-4">-</span>;
  const up = value > 0;
  return (
    <span className={`num ${up ? "text-down" : "text-up"}`}>
      {up ? "▲" : "▼"} {format(Math.abs(value))}
    </span>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: string; children: ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "default" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
};

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  type = "button",
  title,
}: ButtonProps) {
  const classes = { primary: "btn-primary", default: "btn", ghost: "btn-ghost" };
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled} className={classes[variant]}>
      {children}
    </button>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="text-[0.95rem] font-medium text-ink-2">{title}</p>
      {children ? (
        <div className="mx-auto mt-2 max-w-md text-[0.88rem] leading-relaxed text-ink-3">{children}</div>
      ) : null}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="eyebrow mb-2 block">{label}</span>
      {children}
    </label>
  );
}

export const inputClass = "field w-full";

export function Th({
  children,
  align = "left",
  width,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  width?: string;
}) {
  return (
    <th style={width ? { width } : undefined} className={align === "right" ? "align-right" : undefined}>
      {children}
    </th>
  );
}

/* The score a node finished on. Dim when it is high enough to pass, amber when
   it is the reason the run took the escalate or review branch. */
export function StepScore({ value }: { value?: number }) {
  if (value === undefined) return <span className="w-[42px] shrink-0" />;
  return (
    <span
      className={`num w-[42px] shrink-0 text-right ${value < 0.75 ? "text-amber" : "text-ink-4"}`}
      title="confidence when this node finished"
    >
      {value.toFixed(2)}
    </span>
  );
}

/* `email_id` on a record is the Gmail message id, so it deep-links to the
   original. Absent for demo receipts, whose ids are synthetic. */
export function GmailLink({ emailId, connected }: { emailId?: string | null; connected: boolean }) {
  if (!connected || !emailId) return null;
  return (
    <a
      href={`https://mail.google.com/mail/u/0/#all/${encodeURIComponent(emailId)}`}
      target="_blank"
      rel="noreferrer noopener"
      className="text-[0.82rem] text-accent hover:underline"
    >
      Open in Gmail →
    </a>
  );
}

/* The sample-inbox counterpart to GmailLink. A generated receipt has no Gmail
   message to open, so it links to the email the server wrote instead, which is
   what lets a demo visitor check a figure at all. */
export function SampleEmailLink({ emailId, isDemo, label }: { emailId?: string | null; isDemo: boolean; label: string }) {
  if (!isDemo || !emailId) return null;
  return (
    <Link href={`/inbox#${encodeURIComponent(emailId)}`} className="text-[0.82rem] text-accent hover:underline">
      {label} →
    </Link>
  );
}
