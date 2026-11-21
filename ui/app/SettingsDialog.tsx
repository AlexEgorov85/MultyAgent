"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "./i18n";
import { useSettings } from "./SettingsProvider";
import {
  ACCENTS,
  BACKGROUNDS,
  CHAT_FONT_SCALES,
  DEFAULT_AUDITOR_ID,
  DENSITIES,
  FONT_FAMILIES,
  FONT_SCALES,
  RADII,
  THEMES,
  TIME_FORMATS,
  WIDTHS,
  type Accent,
  type ChatBackground,
  type ContentWidth,
  type Density,
  type FontFamily,
  type Radius,
  type ThemeMode,
  type TimeFormat,
} from "./preferences";

const TABS = ["appearance", "behavior", "data", "about"] as const;
type TabId = (typeof TABS)[number];

const ACCENT_COLORS: Record<Accent, string> = {
  indigo: "#6366f1",
  violet: "#8b5cf6",
  emerald: "#10b981",
  amber: "#f59e0b",
  rose: "#f43f5e",
  sky: "#0ea5e9",
};

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

function SettingRow({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div>
        <div className="text-sm font-medium app-text">{title}</div>
        {hint ? (
          <p className="mt-0.5 text-xs leading-relaxed app-muted">{hint}</p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      className="grid gap-1 border app-border app-surface-2 p-1 app-round-sm"
      style={{
        gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))`,
      }}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`app-round-xs px-2 py-1.5 text-xs font-medium transition ${
              active ? "app-segment-active" : "app-segment"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition ${
        checked
          ? "app-accent-gradient border-transparent"
          : "app-surface-2 app-border"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

export function SettingsDialog({
  open,
  onClose,
  onNewChat,
}: {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
}) {
  const { t } = useI18n();
  const { settings, setSetting, resetSettings } = useSettings();
  const [tab, setTab] = useState<TabId>("appearance");
  const [auditorId, setAuditorId] = useState(settings.auditorId);
  const contentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 });
  }, [tab]);

  useEffect(() => {
    if (open) setAuditorId(settings.auditorId);
  }, [open, settings.auditorId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const tabLabels: Record<TabId, string> = {
    appearance: t.appearanceTab,
    behavior: t.behaviorTab,
    data: t.dataTab,
    about: t.aboutTab,
  };

  const themeOptions: { value: ThemeMode; label: string }[] = [
    { value: "light", label: t.themeLight },
    { value: "dark", label: t.themeDark },
    { value: "system", label: t.themeSystem },
  ];

  const accentLabels: Record<Accent, string> = {
    indigo: t.accentIndigo,
    violet: t.accentViolet,
    emerald: t.accentEmerald,
    amber: t.accentAmber,
    rose: t.accentRose,
    sky: t.accentSky,
  };

  const densityOptions: { value: Density; label: string }[] = [
    { value: "compact", label: t.densityCompact },
    { value: "cozy", label: t.densityCozy },
    { value: "comfortable", label: t.densityComfortable },
  ];

  const radiusOptions: { value: Radius; label: string }[] = [
    { value: "sharp", label: t.cornersSharp },
    { value: "soft", label: t.cornersSoft },
    { value: "round", label: t.cornersRound },
  ];

  const widthOptions: { value: ContentWidth; label: string }[] = [
    { value: "narrow", label: t.widthNarrow },
    { value: "normal", label: t.widthNormal },
    { value: "wide", label: t.widthWide },
  ];

  const fontOptions: { value: FontFamily; label: string }[] = [
    { value: "system", label: t.fontSystem },
    { value: "serif", label: t.fontSerif },
    { value: "mono", label: t.fontMono },
  ];

  const backgroundOptions: { value: ChatBackground; label: string }[] = [
    { value: "gradient", label: t.backgroundGradient },
    { value: "plain", label: t.backgroundPlain },
  ];

  const timeFormatOptions: { value: TimeFormat; label: string }[] = [
    { value: "24h", label: t.time24 },
    { value: "12h", label: t.time12 },
  ];

  const commitAuditorId = () => {
    const normalized = auditorId.trim() || DEFAULT_AUDITOR_ID;
    setAuditorId(normalized);
    setSetting("auditorId", normalized);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <div
        className="absolute inset-0 app-overlay app-glass"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        style={{ height: "min(90vh, 720px)" }}
        className="relative flex w-full max-w-[680px] flex-col overflow-hidden border app-card"
      >
        <div className="flex items-center justify-between border-b app-border px-5 py-4">
          <h2 id="settings-title" className="text-base font-semibold app-text">
            {t.settings}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.close}
            title={t.close}
            className="flex h-8 w-8 items-center justify-center rounded-lg app-muted transition app-hover-surface app-hover-text"
          >
            <CloseIcon />
          </button>
        </div>

        <div
          role="tablist"
          aria-label={t.settings}
          className="flex gap-1 overflow-x-auto border-b app-border px-5 py-2"
        >
          {TABS.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={tab === item}
              onClick={() => setTab(item)}
              className={`whitespace-nowrap app-round-sm px-3 py-1.5 text-xs font-medium transition ${
                tab === item
                  ? "app-accent-soft"
                  : "app-muted app-hover-surface app-hover-text"
              }`}
            >
              {tabLabels[item]}
            </button>
          ))}
        </div>

        <div
          ref={contentRef}
          className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
        >
          {tab === "appearance" ? (
            <div className="space-y-5">
              <SettingRow title={t.theme} hint={t.themeHint}>
                <Segmented
                  value={settings.theme}
                  options={themeOptions}
                  onChange={(value) => setSetting("theme", value)}
                />
              </SettingRow>

              <SettingRow title={t.accent} hint={t.accentHint}>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {ACCENTS.map((accent) => {
                    const active = settings.accent === accent;
                    return (
                      <button
                        key={accent}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setSetting("accent", accent)}
                        className={`flex items-center gap-2 border app-round-xs px-2.5 py-2 text-xs font-medium transition ${
                          active
                            ? "app-accent-soft"
                            : "app-surface app-border app-accent-hover"
                        }`}
                      >
                        <span
                          className="h-4 w-4 shrink-0 rounded-full border border-black/10"
                          style={{ backgroundColor: ACCENT_COLORS[accent] }}
                        />
                        <span className="truncate">{accentLabels[accent]}</span>
                      </button>
                    );
                  })}
                </div>
              </SettingRow>

              <SettingRow title={t.fontSize} hint={t.fontSizeHint}>
                <Segmented
                  value={settings.fontScale}
                  options={FONT_SCALES.map((value) => ({
                    value,
                    label: `${Math.round(value * 100)}%`,
                  }))}
                  onChange={(value) => setSetting("fontScale", value)}
                />
              </SettingRow>

              <SettingRow title={t.chatFontSize} hint={t.chatFontSizeHint}>
                <Segmented
                  value={settings.chatFontScale}
                  options={CHAT_FONT_SCALES.map((value) => ({
                    value,
                    label: `${Math.round(value * 100)}%`,
                  }))}
                  onChange={(value) => setSetting("chatFontScale", value)}
                />
              </SettingRow>

              <SettingRow title={t.density} hint={t.densityHint}>
                <Segmented
                  value={settings.density}
                  options={densityOptions}
                  onChange={(value) => setSetting("density", value)}
                />
              </SettingRow>

              <SettingRow title={t.corners} hint={t.cornersHint}>
                <Segmented
                  value={settings.radius}
                  options={radiusOptions}
                  onChange={(value) => setSetting("radius", value)}
                />
              </SettingRow>

              <SettingRow title={t.contentWidth} hint={t.contentWidthHint}>
                <Segmented
                  value={settings.width}
                  options={widthOptions}
                  onChange={(value) => setSetting("width", value)}
                />
              </SettingRow>

              <SettingRow title={t.fontFamily} hint={t.fontFamilyHint}>
                <Segmented
                  value={settings.fontFamily}
                  options={fontOptions}
                  onChange={(value) => setSetting("fontFamily", value)}
                />
              </SettingRow>

              <SettingRow title={t.background} hint={t.backgroundHint}>
                <Segmented
                  value={settings.background}
                  options={backgroundOptions}
                  onChange={(value) => setSetting("background", value)}
                />
              </SettingRow>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow title={t.animations} hint={t.animationsHint}>
                  <span className="text-xs app-muted">
                    {settings.animations ? t.animationsOn : t.animationsOff}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.animations}
                  onChange={(value) => setSetting("animations", value)}
                  label={t.animations}
                />
              </div>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow title={t.glass} hint={t.glassHint}>
                  <span className="text-xs app-muted">
                    {settings.glass ? t.glassOn : t.glassOff}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.glass}
                  onChange={(value) => setSetting("glass", value)}
                  label={t.glass}
                />
              </div>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow title={t.showAvatars} hint={t.showAvatarsHint}>
                  <span className="text-xs app-muted">
                    {settings.showAvatars ? "✓" : "—"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.showAvatars}
                  onChange={(value) => setSetting("showAvatars", value)}
                  label={t.showAvatars}
                />
              </div>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow
                  title={t.showSuggestions}
                  hint={t.showSuggestionsHint}
                >
                  <span className="text-xs app-muted">
                    {settings.showSuggestions ? "✓" : "—"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.showSuggestions}
                  onChange={(value) => setSetting("showSuggestions", value)}
                  label={t.showSuggestions}
                />
              </div>
            </div>
          ) : null}

          {tab === "behavior" ? (
            <div className="space-y-5">
              <SettingRow
                title={t.interfaceLanguage}
                hint={t.interfaceLanguageHint}
              >
                <Segmented
                  value={settings.language}
                  options={[
                    { value: "ru" as const, label: "Русский" },
                    { value: "en" as const, label: "English" },
                  ]}
                  onChange={(value) => setSetting("language", value)}
                />
              </SettingRow>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow title={t.enterToSend} hint={t.enterToSendHint}>
                  <span className="text-xs app-muted">
                    {settings.enterToSend ? "Enter" : "Ctrl + Enter"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.enterToSend}
                  onChange={(value) => setSetting("enterToSend", value)}
                  label={t.enterToSend}
                />
              </div>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow
                  title={t.showTimestamps}
                  hint={t.showTimestampsHint}
                >
                  <span className="text-xs app-muted">
                    {settings.showTimestamps ? "12:34" : "—"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.showTimestamps}
                  onChange={(value) => setSetting("showTimestamps", value)}
                  label={t.showTimestamps}
                />
              </div>

              <SettingRow title={t.timeFormat} hint={t.timeFormatHint}>
                <Segmented
                  value={settings.timeFormat}
                  options={timeFormatOptions}
                  onChange={(value) => setSetting("timeFormat", value)}
                />
              </SettingRow>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow title={t.showOnline} hint={t.showOnlineHint}>
                  <span className="text-xs app-muted">
                    {settings.showOnline ? "online" : "—"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.showOnline}
                  onChange={(value) => setSetting("showOnline", value)}
                  label={t.showOnline}
                />
              </div>

              <div className="flex items-center justify-between gap-4 border-t app-border pt-4">
                <SettingRow
                  title={t.showAgentTrace}
                  hint={t.showAgentTraceHint}
                >
                  <span className="text-xs app-muted">
                    {settings.showAgentTrace ? "✓" : "—"}
                  </span>
                </SettingRow>
                <Toggle
                  checked={settings.showAgentTrace}
                  onChange={(value) => setSetting("showAgentTrace", value)}
                  label={t.showAgentTrace}
                />
              </div>
            </div>
          ) : null}

          {tab === "data" ? (
            <div className="space-y-5">
              <p className="text-xs leading-relaxed app-muted">{t.dataHint}</p>

              <SettingRow title={t.auditor} hint={t.auditorHint}>
                <input
                  id="auditor-id"
                  value={auditorId}
                  onChange={(event) => setAuditorId(event.target.value)}
                  onBlur={commitAuditorId}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.currentTarget.blur();
                    }
                  }}
                  spellCheck={false}
                  autoComplete="off"
                  className="w-full border app-border app-surface app-text app-round-sm px-3 py-2 text-sm transition app-ring"
                />
              </SettingRow>

              <div className="flex flex-wrap gap-2 border-t app-border pt-4">
                <button
                  type="button"
                  onClick={onNewChat}
                  className="border app-border app-surface app-text app-round-sm px-3 py-2 text-xs font-medium transition app-accent-hover"
                >
                  {t.newChat}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(t.resetConfirm)) resetSettings();
                  }}
                  className="app-danger app-round-sm border px-3 py-2 text-xs font-medium transition"
                >
                  {t.resetSettings}
                </button>
              </div>
              <p className="text-xs leading-relaxed app-muted">
                {t.resetSettingsHint}
              </p>
            </div>
          ) : null}

          {tab === "about" ? (
            <div className="space-y-4">
              <div className="border app-border app-surface-2 app-round-sm p-4">
                <h3 className="text-sm font-medium app-text">
                  {t.aboutTitle}
                </h3>
                <p className="mt-1 text-xs leading-relaxed app-muted">
                  {t.aboutDescription}
                </p>
                <p className="mt-2 text-xs leading-relaxed app-muted">
                  {t.aboutStudio}
                </p>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs app-muted">
                <dt>{t.stackLabel}</dt>
                <dd className="app-text">
                  Next.js · assistant-ui · LangGraph
                </dd>
                <dt>{t.versionLabel}</dt>
                <dd className="app-text">{t.versionValue}</dd>
              </dl>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-3 border-t app-border app-surface-2 px-5 py-3">
          <span className="text-[0.7rem] app-muted">
            {t.preferencesSaved}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="border app-border app-surface app-text app-round-sm px-3 py-1.5 text-xs font-medium transition app-accent-hover"
          >
            {t.close}
          </button>
        </div>
      </div>
    </div>
  );
}
