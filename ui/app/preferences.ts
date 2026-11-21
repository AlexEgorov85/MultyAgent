export const LANGUAGES = [
  { code: "ru", label: "Русский", short: "RU" },
  { code: "en", label: "English", short: "EN" },
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];

export const DEFAULT_AUDITOR_ID = "AUD-001";

const LANGUAGE_KEY = "audit-ui-language";
const AUDITOR_KEY = "audit-ui-auditor-id";

export function isLang(value: unknown): value is Lang {
  return LANGUAGES.some((item) => item.code === value);
}

export function readLanguage(): Lang {
  if (typeof window === "undefined") return "ru";
  const stored = window.localStorage.getItem(LANGUAGE_KEY);
  return isLang(stored) ? stored : "ru";
}

export function writeLanguage(lang: Lang): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LANGUAGE_KEY, lang);
}

export function readAuditorId(): string {
  if (typeof window === "undefined") return DEFAULT_AUDITOR_ID;
  const stored = window.localStorage.getItem(AUDITOR_KEY)?.trim();
  return stored ? stored.slice(0, 64) : DEFAULT_AUDITOR_ID;
}

export function writeAuditorId(value: string): void {
  if (typeof window === "undefined") return;
  const normalized = value.trim().slice(0, 64);
  window.localStorage.setItem(
    AUDITOR_KEY,
    normalized || DEFAULT_AUDITOR_ID,
  );
}

export function readPreferences(): {
  language: Lang;
  auditorId: string;
} {
  return { language: readLanguage(), auditorId: readAuditorId() };
}
