"use client";

import { useEffect, useState } from "react";
import { LANGUAGES, useI18n } from "./i18n";
import {
  DEFAULT_AUDITOR_ID,
  readAuditorId,
  writeAuditorId,
} from "./preferences";

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

export function SettingsDialog({
  open,
  onClose,
  onNewChat,
}: {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
}) {
  const { lang, setLang, t } = useI18n();
  const [auditorId, setAuditorId] = useState(DEFAULT_AUDITOR_ID);

  useEffect(() => {
    if (open) setAuditorId(readAuditorId());
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const commitAuditorId = () => {
    const normalized = auditorId.trim() || DEFAULT_AUDITOR_ID;
    setAuditorId(normalized);
    writeAuditorId(normalized);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="relative flex max-h-[90vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2
            id="settings-title"
            className="text-base font-semibold text-slate-900"
          >
            {t.settings}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.close}
            title={t.close}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <section>
            <h3 className="text-sm font-medium text-slate-900">
              {t.interfaceLanguage}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {t.interfaceLanguageHint}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {LANGUAGES.map((option) => {
                const active = option.code === lang;
                return (
                  <button
                    key={option.code}
                    type="button"
                    onClick={() => setLang(option.code)}
                    aria-pressed={active}
                    className={
                      active
                        ? "flex items-center justify-between rounded-xl border border-indigo-300 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700"
                        : "flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
                    }
                  >
                    <span>{option.label}</span>
                    <span className="text-[0.7rem] font-semibold tracking-wide text-slate-400">
                      {option.short}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <label
              htmlFor="auditor-id"
              className="text-sm font-medium text-slate-900"
            >
              {t.auditor}
            </label>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {t.auditorHint}
            </p>
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
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            />
          </section>

          <section className="rounded-xl bg-slate-50 p-3">
            <h3 className="text-sm font-medium text-slate-900">
              {t.aboutTitle}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-slate-600">
              {t.aboutDescription}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              {t.aboutStudio}
            </p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-slate-600">
              <dt className="text-slate-500">{t.stackLabel}</dt>
              <dd>Next.js · assistant-ui · LangGraph</dd>
              <dt className="text-slate-500">{t.versionLabel}</dt>
              <dd>{t.versionValue}</dd>
            </dl>
          </section>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <span className="text-[0.7rem] text-slate-500">
            {t.preferencesSaved}
          </span>
          <button
            type="button"
            onClick={onNewChat}
            className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700"
          >
            {t.newChat}
          </button>
        </div>
      </div>
    </div>
  );
}
