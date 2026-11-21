"use client";

import {
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import { useCallback, useState } from "react";
import { SettingsDialog } from "./SettingsDialog";
import { LANGUAGES, useI18n } from "./i18n";

function GearIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.94 19.3a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.7 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.7 8.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.7a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.7a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.3 9c.13.62.66 1.08 1.29 1.08H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z" />
    </svg>
  );
}

function MenuIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="ml-auto max-w-[85%]">
      <div className="rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-[0.95rem] leading-relaxed text-white shadow-sm">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const { t } = useI18n();

  return (
    <MessagePrimitive.Root className="mr-auto max-w-[92%]">
      <div className="flex gap-3">
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-xs font-bold text-white shadow">
          {t.assistantInitial}
        </div>
        <div className="min-w-0 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-[0.95rem] leading-relaxed text-slate-800 shadow-sm">
          <div className="aui-text">
            <MessagePrimitive.Parts />
          </div>
          <MessagePrimitive.Error>
            <div className="mt-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-700">
              <div className="font-semibold">{t.errorTitle}</div>
              <div className="mt-0.5">{t.errorHint}</div>
            </div>
          </MessagePrimitive.Error>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function EmptyState() {
  const { t } = useI18n();

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl text-white shadow-lg">
        {t.assistantInitial}
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        {t.emptyTitle}
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-500">
        {t.emptyDescription}
      </p>
      <div className="mt-7 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {t.suggestions.map((item) => (
          <ThreadPrimitive.Suggestion
            key={item.title}
            prompt={item.text}
            send
            className="rounded-xl border border-slate-200 bg-white/80 px-4 py-3 text-left transition hover:border-indigo-300 hover:bg-white hover:shadow-sm"
          >
            <div className="text-sm font-medium text-slate-800">{item.title}</div>
            <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">
              {item.text}
            </div>
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </div>
  );
}

function ThinkingStatus() {
  const { t } = useI18n();
  const running = useAuiState((state) => state.thread.isRunning);

  if (!running) return null;

  return (
    <div className="mb-2 flex items-center justify-center gap-2 text-xs text-indigo-600">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
      {t.thinking}
    </div>
  );
}

function HeaderMenu({
  onSettings,
  onNewChat,
}: {
  onSettings: () => void;
  onNewChat: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  const run = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <div className="relative z-40">
      {open ? (
        <div
          className="fixed inset-0 z-30"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      ) : null}
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t.menuHint}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white/80 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
      >
        <MenuIcon className="h-4 w-4" />
        <span className="hidden sm:inline">{t.menu}</span>
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-1 w-48 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 text-sm shadow-xl"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => run(onNewChat)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-700 transition hover:bg-slate-50"
          >
            <span className="text-base leading-none">＋</span>
            {t.newChat}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => run(onSettings)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-700 transition hover:bg-slate-50"
          >
            <GearIcon className="h-4 w-4" />
            {t.settings}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function Home() {
  const { lang, setLang, t } = useI18n();
  const aui = useAui();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleNewChat = useCallback(() => {
    try {
      aui.threads.switchToNewThread();
    } catch {
      aui.thread.reset();
    }
    setSettingsOpen(false);
  }, [aui]);

  return (
    <div className="flex h-dvh flex-col">
      <header className="border-b border-slate-200/70 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white shadow">
            {t.assistantInitial}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900">
              {t.appTitle}
            </div>
            <div className="truncate text-[0.7rem] text-slate-500">
              {t.tagline}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[0.7rem] font-medium text-emerald-700 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {t.online}
            </div>
            <button
              type="button"
              onClick={() => setLang(lang === "ru" ? "en" : "ru")}
              aria-label={t.interfaceLanguage}
              title={t.interfaceLanguage}
              className="rounded-xl border border-slate-200 bg-white/80 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700"
            >
              {LANGUAGES.find((item) => item.code === lang)?.short ??
                lang.toUpperCase()}
            </button>
            <HeaderMenu
              onSettings={() => setSettingsOpen(true)}
              onNewChat={handleNewChat}
            />
          </div>
        </div>
      </header>

      <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
        <ThreadPrimitive.Viewport className="aui-scrollbar flex-1 overflow-y-auto">
          <ThreadPrimitive.Empty>
            <EmptyState />
          </ThreadPrimitive.Empty>
          <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-6">
            <ThreadPrimitive.Messages>
              {({ message }) =>
                message.role === "user" ? <UserMessage /> : <AssistantMessage />
              }
            </ThreadPrimitive.Messages>
          </div>
        </ThreadPrimitive.Viewport>

        <ThreadPrimitive.ViewportFooter className="border-t border-slate-200/70 bg-white/80 px-4 py-3 backdrop-blur">
          <div className="mx-auto max-w-4xl">
            <ThinkingStatus />
            <ComposerPrimitive.Root className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100">
              <ComposerPrimitive.Input
                placeholder={t.placeholder}
                rows={1}
                className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] text-slate-900 outline-none placeholder:text-slate-400"
              />
              <ComposerPrimitive.Send className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">
                {t.send}
              </ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
            <div className="mt-2 text-center text-[0.68rem] text-slate-400">
              {t.disclaimer}
            </div>
          </div>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Root>

      <button
        type="button"
        onClick={() => setSettingsOpen(true)}
        aria-label={t.settings}
        title={t.settings}
        className="fixed bottom-24 left-4 z-40 flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-slate-600 shadow-lg backdrop-blur transition hover:border-indigo-300 hover:text-indigo-600 sm:bottom-4"
      >
        <GearIcon />
      </button>

      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onNewChat={handleNewChat}
      />
    </div>
  );
}
