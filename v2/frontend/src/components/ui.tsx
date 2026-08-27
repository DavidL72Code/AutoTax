import { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-[6px] border border-line bg-surface ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <h2 className="text-[13px] font-medium text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="rounded-[6px] border border-line bg-surface px-4 py-3.5">
      <div className="text-[12px] text-ink-3">{label}</div>
      <div className="num mt-1 text-[26px] leading-none font-medium tracking-[-0.02em] text-ink">{value}</div>
      {hint ? <div className="mt-1.5 text-[12px] text-ink-3">{hint}</div> : null}
    </div>
  );
}

const badgeStyles: Record<string, string> = {
  parsed: "border-line bg-canvas text-ink-2",
  needs_review: "border-warn/25 bg-warn-soft text-warn",
  skipped: "border-line bg-canvas text-ink-3",
  failed: "border-danger/25 bg-surface text-danger",
  accent: "border-accent/25 bg-accent-soft text-accent-ink",
};

export function Badge({ tone = "parsed", children }: { tone?: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-[4px] border px-1.5 py-0.5 text-[11px] leading-4 ${
        badgeStyles[tone] ?? badgeStyles.parsed
      }`}
    >
      {children}
    </span>
  );
}

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "default" | "quiet";
  size?: "sm" | "md";
  disabled?: boolean;
  type?: "button" | "submit";
};

export function Button({
  children,
  onClick,
  variant = "default",
  size = "md",
  disabled,
  type = "button",
}: ButtonProps) {
  const variants = {
    primary: "bg-accent text-white border-accent hover:bg-accent-ink",
    default: "bg-surface text-ink border-line-strong hover:bg-canvas",
    quiet: "bg-transparent text-ink-2 border-transparent hover:bg-canvas hover:text-ink",
  };
  const sizes = { sm: "h-7 px-2.5 text-[12px]", md: "h-8 px-3 text-[13px]" };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-[5px] border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]} ${sizes[size]}`}
    >
      {children}
    </button>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {children ? <div className="mx-auto mt-1.5 max-w-sm text-[13px] text-ink-3">{children}</div> : null}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] text-ink-3">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "h-8 rounded-[5px] border border-line-strong bg-surface px-2 text-[13px] text-ink placeholder:text-ink-3";
