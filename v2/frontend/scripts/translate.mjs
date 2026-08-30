#!/usr/bin/env node
/**
 * Generate a locale file from en.json.
 *
 *   GOOGLE_API_KEY=... node scripts/translate.mjs vi "Tiếng Việt"
 *   GOOGLE_API_KEY=... node scripts/translate.mjs de Deutsch --force
 *
 * Only keys missing from the target file are sent, so re-running after adding a
 * string translates that string and leaves reviewed text alone. `--force`
 * retranslates everything.
 *
 * This is a first draft, not a shipped translation. The output is committed so
 * it can be reviewed and corrected in a diff by someone who reads the language
 * — that review is the point, and the model only removes the blank-page step.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = resolve(here, "../src/lib/i18n");
const [code, name, ...flags] = process.argv.slice(2);
const force = flags.includes("--force");

if (!code || !name) {
  console.error('usage: node scripts/translate.mjs <code> <native name> [--force]');
  process.exit(1);
}

const key = process.env.GOOGLE_API_KEY;
if (!key) {
  console.error("GOOGLE_API_KEY is not set — it is the same key the backend uses.");
  process.exit(1);
}

const en = JSON.parse(readFileSync(resolve(dir, "en.json"), "utf8"));
const target = resolve(dir, `${code}.json`);
const existing = !force && existsSync(target) ? JSON.parse(readFileSync(target, "utf8")) : {};
const todo = Object.fromEntries(Object.entries(en).filter(([k]) => !(k in existing)));

if (!Object.keys(todo).length) {
  console.log(`${code}: already complete (${Object.keys(existing).length} keys)`);
  process.exit(0);
}

const INSTRUCTIONS = `You are translating the interface of a receipt-bookkeeping app into ${name}.

Return ONLY a JSON object mapping each key to its translation. No prose, no code fence.

Rules:
- Keep every {placeholder} exactly as written. Never translate, reorder the spelling of, or drop one.
- Reorder the words AROUND placeholders so the sentence is natural in ${name}. Do not preserve English word order.
- Keys under "trace." are short technical log lines shown to a person auditing a parse. Keep them terse and lowercase if that suits the language.
- Keys under "issue." are problems with a receipt, phrased as a short statement.
- Do not translate these product terms: Gmail, Google, ReceiptAuto, CSV, API, Fernet, await_review, validate.
- Currency amounts arrive pre-formatted in a placeholder; do not add symbols.
- Use the register of a careful professional tool, not marketing copy.`;

const body = {
  contents: [{ role: "user", parts: [{ text: `${INSTRUCTIONS}\n\n${JSON.stringify(todo, null, 2)}` }] }],
  generationConfig: { temperature: 0.2, responseMimeType: "application/json", maxOutputTokens: 16384 },
};

const model = process.env.GEMINI_MODEL || "gemini-3.1-flash-lite";
const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`;

const response = await fetch(url, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

if (!response.ok) {
  console.error(`${model} returned ${response.status}: ${(await response.text()).slice(0, 400)}`);
  process.exit(1);
}

const payload = await response.json();
const text = payload.candidates?.[0]?.content?.parts?.map((p) => p.text).join("") ?? "";
let translated;
try {
  translated = JSON.parse(text.replace(/^```json\s*|\s*```$/g, ""));
} catch {
  console.error("could not parse the model's reply as JSON:\n", text.slice(0, 400));
  process.exit(1);
}

// A translation that lost a placeholder would render a broken sentence, so it
// is rejected per key rather than accepted and shipped.
const placeholders = (s) => (String(s).match(/\{\w+\}/g) ?? []).sort().join(",");
const merged = { ...existing };
const dropped = [];
for (const [k, v] of Object.entries(translated)) {
  if (!(k in en) || typeof v !== "string") continue;
  if (placeholders(v) !== placeholders(en[k])) {
    dropped.push(k);
    continue;
  }
  merged[k] = v;
}

const missing = Object.keys(en).filter((k) => !(k in merged));
merged["locale.name"] = name;

mkdirSync(dir, { recursive: true });
writeFileSync(target, `${JSON.stringify(merged, null, 2)}\n`);

console.log(`${code}: ${Object.keys(merged).length}/${Object.keys(en).length} keys -> src/lib/i18n/${code}.json`);
if (dropped.length) console.log(`  rejected (placeholder mismatch): ${dropped.join(", ")}`);
if (missing.length) console.log(`  still missing: ${missing.join(", ")}`);
console.log(`  add to LOCALES in src/lib/i18n/index.tsx, then have a speaker review the diff.`);
