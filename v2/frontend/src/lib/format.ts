/* Formatting is not translation. `Intl` knows that Spanish writes 1.234,56 and
   puts the month after the day; it has no opinion about the word "Vendor".
   Everything here is the first job, and needs no model, but it does need to
   know the reader's locale, which is why it is settable rather than pinned.

   The ledger's amounts are dollars regardless of who is reading, so the
   currency stays USD and only its presentation follows the locale. */
let locale = "en-US";
let currency = build("standard");
let compact = build("compact");

function build(notation: "standard" | "compact") {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    notation,
    maximumFractionDigits: notation === "compact" ? 1 : 2,
  });
}

/** Called by the i18n provider when the reader picks a language. */
export function setFormatLocale(next: string) {
  locale = next;
  currency = build("standard");
  compact = build("compact");
}

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "\u2014";
  return currency.format(Number(value));
}

export function moneyCompact(value: number): string {
  return compact.format(value);
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return "\u2014";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" });
}

export function monthLabel(value: string): string {
  const parsed = new Date(`${value}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(locale, { month: "short" });
}

/* Plural choice is a language rule, not a translation. English has two forms,
   Spanish two, Polish four, Japanese one, `Intl.PluralRules` knows which form
   a number takes so the locale file can carry one key per form instead of the
   "(s)" fudge. */
export function plural(count: number, forms: Record<string, string>): string {
  const category = new Intl.PluralRules(locale).select(count);
  return forms[category] ?? forms.other ?? "";
}
