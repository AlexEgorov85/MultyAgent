"use client";

import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { useCallback, useState } from "react";
import { AgentTrace } from "./AgentTrace";
import { MarkdownText } from "./MarkdownText";
import { ChatSidebar } from "./ChatSidebar";
import { useChats } from "./chats";
import { SettingsDialog } from "./SettingsDialog";
import { useSettings } from "./SettingsProvider";
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

function ChatListIcon({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 9 9 0 0 1-3.8-.8L3 21l1.8-5.2A8.4 8.4 0 0 1 12.5 3 8.4 8.4 0 0 1 21 11.5Z" />
      <path d="M8 10h8M8 14h5" />
    </svg>
  );
}

function MessageTimestamp() {
  const { settings } = useSettings();
  const { lang } = useI18n();
  const createdAt = useAuiState((state) => state.message.createdAt);

  if (!settings.showTimestamps || !createdAt) return null;

  const date = new Date(createdAt as string | number | Date);
  if (Number.isNaN(date.getTime())) return null;

  const text = new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: settings.timeFormat === "12h",
  }).format(date);

  return <div className="mt-1 text-[0.65rem] app-muted-2">{text}</div>;
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="ml-auto max-w-[85%]">
      <div className="app-user-bubble app-bubble app-round app-chat-text shadow-sm">
        <MessagePrimitive.Parts />
        <MessageTimestamp />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const { t } = useI18n();
  const { settings } = useSettings();
  const emptyRunning = useAuiState(
    (state) =>
      state.message.role === "assistant" &&
      state.message.status?.type === "running" &&
      !state.message.parts.some(
        (part) => part.type === "text" && part.text.trim().length > 0,
      ),
  );

  if (emptyRunning) {
    return (
      <MessagePrimitive.Root className="mr-auto max-w-[92%]">
        <div className="flex gap-3">
          {settings.showAvatars ? (
            <div className="app-accent-gradient mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold shadow">
              {t.assistantInitial}
            </div>
          ) : null}
          <div className="app-assistant-bubble app-bubble app-round min-w-0 border px-4 py-3 shadow-sm">
            <div className="flex items-center gap-2 text-xs app-muted">
              <span>{t.thinking}</span>
              <ThinkingDots />
            </div>
          </div>
        </div>
      </MessagePrimitive.Root>
    );
  }

  return (
    <MessagePrimitive.Root className="mr-auto max-w-[92%]">
      <div className="flex gap-3">
        {settings.showAvatars ? (
          <div className="app-accent-gradient mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold shadow">
            {t.assistantInitial}
          </div>
        ) : null}
        <div className="app-assistant-bubble app-bubble app-round min-w-0 border shadow-sm">
          <div className="aui-text app-chat-text">
            <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
          </div>
          <MessagePrimitive.Error>
            <div className="app-danger app-round-sm mt-2 border px-3 py-2 text-xs leading-relaxed">
              <div className="font-semibold">{t.errorTitle}</div>
              <div className="mt-0.5">{t.errorHint}</div>
            </div>
          </MessagePrimitive.Error>
          {settings.showAgentTrace ? <AgentTrace /> : null}
          <MessageTimestamp />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function EmptyState() {
  const { t } = useI18n();
  const { settings } = useSettings();

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <div className="app-accent-gradient app-round mb-5 flex h-14 w-14 items-center justify-center text-2xl shadow-lg">
        {t.assistantInitial}
      </div>
      <h1 className="text-2xl font-semibold tracking-tight app-text">
        {t.emptyTitle}
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed app-muted">
        {t.emptyDescription}
      </p>
      <div className="mt-7 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {settings.showSuggestions
          ? t.suggestions.map((item) => (
              <ThreadPrimitive.Suggestion
                key={item.title}
                prompt={item.text}
                send
                className="app-surface app-border app-round-sm border px-4 py-3 text-left transition app-accent-hover hover:shadow-sm"
              >
                <div className="text-sm font-medium app-text">
                  {item.title}
                </div>
                <div className="mt-0.5 line-clamp-2 text-xs app-muted">
                  {item.text}
                </div>
              </ThreadPrimitive.Suggestion>
            ))
          : null}
      </div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="flex items-center gap-1" aria-hidden="true">
      <span className="app-thinking-dot app-accent-dot h-1.5 w-1.5 rounded-full" />
      <span className="app-thinking-dot app-accent-dot h-1.5 w-1.5 rounded-full" />
      <span className="app-thinking-dot app-accent-dot h-1.5 w-1.5 rounded-full" />
    </span>
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
        className="app-surface app-border app-muted app-round-sm flex items-center gap-1.5 border px-2.5 py-1.5 text-xs font-medium transition app-accent-hover"
      >
        <MenuIcon className="h-4 w-4" />
        <span className="hidden sm:inline">{t.menu}</span>
      </button>
      {open ? (
        <div
          role="menu"
          className="app-surface app-border app-round-sm absolute right-0 z-40 mt-1 w-48 overflow-hidden border py-1 text-sm shadow-xl"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => run(onNewChat)}
            className="app-menu-item flex w-full items-center gap-2 px-3 py-2 text-left transition"
          >
            <span className="text-base leading-none">＋</span>
            {t.newChat}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => run(onSettings)}
            className="app-menu-item flex w-full items-center gap-2 px-3 py-2 text-left transition"
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
  const { settings } = useSettings();
  const { newChat, activeChat } = useChats();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatsOpen, setChatsOpen] = useState(false);

  const handleNewChat = useCallback(() => {
    newChat();
    setSettingsOpen(false);
    setChatsOpen(false);
  }, [newChat]);

  return (
    <div className="flex h-dvh overflow-hidden">
      <ChatSidebar
        open={chatsOpen}
        onClose={() => setChatsOpen(false)}
        onSettings={() => {
          setChatsOpen(false);
          setSettingsOpen(true);
        }}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <header className="app-header app-glass border-b">
          <div className="app-shell app-header-pad mx-auto flex items-center gap-2 px-4">
            <button
              type="button"
              onClick={() => setChatsOpen(true)}
              aria-label={t.openChats}
              title={t.openChats}
              className="app-surface app-border app-muted app-round-sm flex items-center gap-1.5 border px-2 py-1.5 text-xs font-medium transition app-accent-hover lg:hidden"
            >
              <ChatListIcon className="h-4 w-4" />
              <span className="hidden sm:inline">{t.chats}</span>
            </button>
            <div className="app-accent-gradient app-round-sm flex h-9 w-9 shrink-0 items-center justify-center text-sm font-bold shadow">
              {t.assistantInitial}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold app-text">
                {t.appTitle}
              </div>
              <div className="truncate text-[0.7rem] app-muted">
                {t.tagline}
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              {settings.showOnline ? (
                <div className="app-online hidden items-center gap-2 rounded-full border px-3 py-1 text-[0.7rem] font-medium sm:flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  {t.online}
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => setLang(lang === "ru" ? "en" : "ru")}
                aria-label={t.interfaceLanguage}
                title={t.interfaceLanguage}
                className="app-surface app-border app-muted app-round-sm border px-2.5 py-1.5 text-xs font-semibold transition app-accent-hover"
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

        <ThreadPrimitive.Root
          key={activeChat?.id ?? "empty"}
          className="flex min-h-0 flex-1 flex-col"
        >
          <ThreadPrimitive.Viewport
            scrollToBottomOnInitialize
            scrollToBottomOnThreadSwitch
            className="aui-scrollbar flex-1 overflow-y-auto"
          >
            <ThreadPrimitive.Empty>
              <EmptyState />
            </ThreadPrimitive.Empty>
            <div className="app-shell app-msg-gap mx-auto flex flex-col px-4 py-6">
              <ThreadPrimitive.Messages>
                {({ message }) =>
                  message.role === "user" ? <UserMessage /> : <AssistantMessage />
                }
              </ThreadPrimitive.Messages>
            </div>
          </ThreadPrimitive.Viewport>

          <ThreadPrimitive.ViewportFooter className="app-footer app-glass border-t px-4 app-footer-pad">
            <div className="app-shell mx-auto">
              <ComposerPrimitive.Root className="app-surface app-border app-composer-pad app-round app-ring flex items-end gap-2 border shadow-sm">
                <ComposerPrimitive.Input
                  placeholder={t.placeholder}
                  rows={1}
                  submitMode={settings.enterToSend ? "enter" : "ctrlEnter"}
                  className="app-input app-text max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] outline-none"
                />
                <ComposerPrimitive.Send className="app-primary app-round-sm px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40">
                  {t.send}
                </ComposerPrimitive.Send>
              </ComposerPrimitive.Root>
              <div className="mt-2 text-center text-[0.68rem] app-muted-2">
                {t.disclaimer}
              </div>
            </div>
          </ThreadPrimitive.ViewportFooter>
        </ThreadPrimitive.Root>
      </div>

      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onNewChat={handleNewChat}
      />
    </div>
  );
}
