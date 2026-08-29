/* The logo is a real asset, `public/brand/mark.svg`, not shapes drawn inline
   in JSX. One file to swap, and the favicon carries the same construction.

   Rendered with a plain <img> rather than next/image on purpose: next/image
   refuses SVG sources unless `dangerouslyAllowSVG` is set in next.config, and a
   400-byte flat path gains nothing from the optimiser. */

export function Mark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/brand/mark.svg"
      width={size}
      height={size}
      alt="ReceiptAuto"
      className={`shrink-0 ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

/* Set in caps with open tracking, which is what Porsche, YSL and Chase have in
   common typographically: the mark is geometric, so the type should be
   architectural rather than friendly. Live text, not baked into the SVG: an
   <img>-loaded SVG cannot reach the page's fonts. */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`font-[family-name:var(--font-display)] font-bold tracking-[0.08em] text-ink ${className}`}
    >
      RECEIPT<span className="text-brand">AUTO</span>
    </span>
  );
}

export function Lockup({ size = 30 }: { size?: number }) {
  return (
    <span className="flex items-center gap-3">
      <Mark size={size} />
      <Wordmark className="text-[0.95rem]" />
    </span>
  );
}
