export const LANGUAGES = [
  { code: "ru", label: "Русский", short: "RU" },
  { code: "en", label: "English", short: "EN" },
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];

export const THEMES = ["light", "dark", "system"] as const;
export type ThemeMode = (typeof THEMES)[number];

export const ACCENTS = [
  "indigo",
  "violet",
  "emerald",
  "amber",
  "rose",
  "sky",
] as const;
export type Accent = (typeof ACCENTS)[number];

export const DENSITIES = ["compact", "cozy", "comfortable"] as const;
export type Density = (typeof DENSITIES)[number];

export const RADII = ["sharp", "soft", "round"] as const;
export type Radius = (typeof RADII)[number];

export const WIDTHS = ["narrow", "normal", "wide"] as const;
export type ContentWidth = (typeof WIDTHS)[number];

export const FONT_FAMILIES = ["system", "serif", "mono"] as const;
export type FontFamily = (typeof FONT_FAMILIES)[number];

export const BACKGROUNDS = ["gradient", "plain"] as const;
export type ChatBackground = (typeof BACKGROUNDS)[number];

export const TIME_FORMATS = ["24h", "12h"] as const;
export type TimeFormat = (typeof TIME_FORMATS)[number];

export const FONT_SCALES = [0.9, 1, 1.1, 1.2] as const;
export const CHAT_FONT_SCALES = [0.9, 1, 1.1, 1.2] as const;

export const DEFAULT_AUDITOR_ID = "AUD-001";

export type UiPreferences = {
  language: Lang;
  auditorId: string;
  theme: ThemeMode;
  accent: Accent;
  fontScale: number;
  chatFontScale: number;
  density: Density;
  radius: Radius;
  width: ContentWidth;
  fontFamily: FontFamily;
  background: ChatBackground;
  animations: boolean;
  glass: boolean;
  enterToSend: boolean;
  showTimestamps: boolean;
  timeFormat: TimeFormat;
  showAvatars: boolean;
  showSuggestions: boolean;
  showOnline: boolean;
  showAgentTrace: boolean;
};

export const DEFAULT_PREFERENCES: UiPreferences = {
  language: "ru",
  auditorId: DEFAULT_AUDITOR_ID,
  theme: "light",
  accent: "indigo",
  fontScale: 1,
  chatFontScale: 1,
  density: "cozy",
  radius: "soft",
  width: "normal",
  fontFamily: "system",
  background: "gradient",
  animations: true,
  glass: true,
  enterToSend: true,
  showTimestamps: false,
  timeFormat: "24h",
  showAvatars: true,
  showSuggestions: true,
  showOnline: true,
  showAgentTrace: true,
};

const SETTINGS_KEY = "audit-ui-preferences";
const LANGUAGE_KEY = "audit-ui-language";
const AUDITOR_KEY = "audit-ui-auditor-id";

function oneOf<T extends readonly (string | number)[]>(
  value: unknown,
  options: T,
  fallback: T[number],
): T[number] {
  return options.includes(value as T[number]) ? (value as T[number]) : fallback;
}

function clampScale(value: unknown, fallback: number): number {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(1.2, Math.max(0.9, Math.round(number * 100) / 100));
}

function bool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function isLang(value: unknown): value is Lang {
  return LANGUAGES.some((item) => item.code === value);
}

export function sanitizePreferences(value: unknown): UiPreferences {
  const source = value && typeof value === "object" ? value : {};
  const data = source as Partial<Record<keyof UiPreferences, unknown>>;
  return {
    language: isLang(data.language)
      ? data.language
      : DEFAULT_PREFERENCES.language,
    auditorId:
      typeof data.auditorId === "string" && data.auditorId.trim()
        ? data.auditorId.trim().slice(0, 64)
        : DEFAULT_AUDITOR_ID,
    theme: oneOf(data.theme, THEMES, DEFAULT_PREFERENCES.theme),
    accent: oneOf(data.accent, ACCENTS, DEFAULT_PREFERENCES.accent),
    fontScale: clampScale(data.fontScale, DEFAULT_PREFERENCES.fontScale),
    chatFontScale: clampScale(
      data.chatFontScale,
      DEFAULT_PREFERENCES.chatFontScale,
    ),
    density: oneOf(data.density, DENSITIES, DEFAULT_PREFERENCES.density),
    radius: oneOf(data.radius, RADII, DEFAULT_PREFERENCES.radius),
    width: oneOf(data.width, WIDTHS, DEFAULT_PREFERENCES.width),
    fontFamily: oneOf(
      data.fontFamily,
      FONT_FAMILIES,
      DEFAULT_PREFERENCES.fontFamily,
    ),
    background: oneOf(
      data.background,
      BACKGROUNDS,
      DEFAULT_PREFERENCES.background,
    ),
    animations: bool(data.animations, DEFAULT_PREFERENCES.animations),
    glass: bool(data.glass, DEFAULT_PREFERENCES.glass),
    enterToSend: bool(data.enterToSend, DEFAULT_PREFERENCES.enterToSend),
    showTimestamps: bool(
      data.showTimestamps,
      DEFAULT_PREFERENCES.showTimestamps,
    ),
    timeFormat: oneOf(
      data.timeFormat,
      TIME_FORMATS,
      DEFAULT_PREFERENCES.timeFormat,
    ),
    showAvatars: bool(data.showAvatars, DEFAULT_PREFERENCES.showAvatars),
    showSuggestions: bool(
      data.showSuggestions,
      DEFAULT_PREFERENCES.showSuggestions,
    ),
    showOnline: bool(data.showOnline, DEFAULT_PREFERENCES.showOnline),
    showAgentTrace: bool(
      data.showAgentTrace,
      DEFAULT_PREFERENCES.showAgentTrace,
    ),
  };
}

export function readUiPreferences(): UiPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    const legacyLanguage = window.localStorage.getItem(LANGUAGE_KEY);
    const legacyAuditor = window.localStorage.getItem(AUDITOR_KEY);
    return sanitizePreferences({
      ...DEFAULT_PREFERENCES,
      ...(legacyLanguage ? { language: legacyLanguage } : {}),
      ...(legacyAuditor ? { auditorId: legacyAuditor } : {}),
      ...parsed,
    });
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function writeUiPreferences(preferences: UiPreferences): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(preferences));
  window.localStorage.setItem(LANGUAGE_KEY, preferences.language);
  window.localStorage.setItem(AUDITOR_KEY, preferences.auditorId);
}

export function readLanguage(): Lang {
  return readUiPreferences().language;
}

export function writeLanguage(lang: Lang): void {
  writeUiPreferences({ ...readUiPreferences(), language: lang });
}

export function readAuditorId(): string {
  return readUiPreferences().auditorId;
}

export function writeAuditorId(value: string): void {
  const normalized = value.trim().slice(0, 64) || DEFAULT_AUDITOR_ID;
  writeUiPreferences({ ...readUiPreferences(), auditorId: normalized });
}

export function readPreferences(): {
  language: Lang;
  auditorId: string;
} {
  const preferences = readUiPreferences();
  return {
    language: preferences.language,
    auditorId: preferences.auditorId,
  };
}
