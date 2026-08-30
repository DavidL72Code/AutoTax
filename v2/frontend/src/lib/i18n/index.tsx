"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en from "./en.json";
import { setFormatLocale } from "@/lib/format";

/* Every string the app can show lives in a locale file keyed the same way, so
   "is this translated?" is answerable by diffing key sets rather than by
   reading the UI. `en.json` is the contract: a locale missing a key falls back
   to English for that key alone, never to a blank. */
export type Dict = Record<string, string>;

/* Registered locales. A new language is a new JSON file plus one line here, see scripts/translate.mjs, which generates a file from en.json. */
export const LOCALES: Record<string, { name: string; load: () => Promise<{ default: Dict }> }> = {
  en: { name: "English", load: async () => ({ default: en as Dict }) },
  es: { name: "Español", load: () => import("./es.json") as Promise<{ default: Dict }> },
};

const KEY = "receiptauto:locale";

/** `{name}` placeholders, filled from a values object. Missing values render as
    the placeholder rather than "undefined", which makes a bad key obvious. */
function interpolate(template: string, params?: Record<string, unknown>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) => {
    const value = params[name];
    if (value === undefined || value === null) return whole;
    return Array.isArray(value) ? value.join(", ") : String(value);
  });
}

type Ctx = {
  locale: string;
  setLocale: (next: string) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
};

const I18n = createContext<Ctx>({ locale: "en", setLocale: () => {}, t: (k) => k });

function pickInitial(): string {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(KEY);
  if (stored && LOCALES[stored]) return stored;
  // Match the browser's preference on first visit, longest tag first so
  // zh-Hans wins over a bare zh.
  for (const tag of navigator.languages ?? []) {
    if (LOCALES[tag]) return tag;
    const base = tag.split("-")[0];
    const match = Object.keys(LOCALES).find((code) => code.split("-")[0] === base);
    if (match) return match;
  }
  return "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setState] = useState("en");
  const [dict, setDict] = useState<Dict>(en as Dict);

  useEffect(() => {
    setState(pickInitial());
  }, []);

  useEffect(() => {
    let cancelled = false;
    document.documentElement.lang = locale;
    setFormatLocale(locale);
    LOCALES[locale]
      ?.load()
      .then((mod) => {
        if (!cancelled) setDict(mod.default);
      })
      .catch(() => {
        if (!cancelled) setDict(en as Dict);
      });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  const setLocale = useCallback((next: string) => {
    if (!LOCALES[next]) return;
    setState(next);
    localStorage.setItem(KEY, next);
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, unknown>) =>
      interpolate(dict[key] ?? (en as Dict)[key] ?? key, params),
    [dict],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useT = () => useContext(I18n);

/** A trace step, an issue code or a finding renders from its key when the
    backend sent one, and from the English sentence when it did not. */
/* Some params are themselves translatable: a field source, a triage reason, a
   status. They arrive as codes and are looked up before interpolation, so
   "vendor Netflix, via domain" becomes "via sender domain" in every language
   rather than leaking the raw code. */
const LOOKUP: Record<string, string> = {
  source: "source",
  reason: "reason",
  status: "status",
  category: "category",
  how: "how",
};

export function useTrace() {
  const { t } = useT();
  return useCallback(
    (step: { key?: string; params?: Record<string, unknown>; detail: string }) => {
      if (!step.key) return step.detail;
      const params: Record<string, unknown> = { ...(step.params ?? {}) };
      const lookup = (prefix: string, value: string) => {
        const looked = t(`${prefix}.${value}`);
        return looked === `${prefix}.${value}` ? value : looked;
      };
      for (const [name, prefix] of Object.entries(LOOKUP)) {
        const value = params[name];
        if (typeof value === "string") params[name] = lookup(prefix, value);
      }
      // `issues` and `fields` arrive as arrays of codes; each element is
      // translatable on its own, and joining raw codes is how "amount_missing,
      // model_unavailable" ends up in front of a reader.
      if (Array.isArray(params.issues)) {
        params.issues = (params.issues as string[]).map((code) => lookup("issue", code));
      }
      // The triage templates read {why}; the backend sends the code as `reason`.
      if (params.reason !== undefined && params.why === undefined) params.why = params.reason;
      return t(step.key, params);
    },
    [t],
  );
}
