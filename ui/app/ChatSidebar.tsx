"use client";

import { useEffect, useRef, useState } from "react";
import { useChats } from "./chats";
import { useI18n } from "./i18n";

function PlusIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function TrashIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13M10 11v5M14 11v5" />
    </svg>
  );
}

function PencilIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
      <path d="m13.5 6.5 3 3" />
    </svg>
  );
}

function CloseIcon({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

function GearIcon({ className = "h-4 w-4" }: { className?: string }) {
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

export function ChatSidebar({
  open,
  onClose,
  onSettings,
}: {
  open: boolean;
  onClose: () => void;
  onSettings: () => void;
}) {
  const { t, lang } = useI18n();
  const {
    chats,
    activeId,
    ready,
    newChat,
    switchChat,
    renameChat,
    deleteChat,
  } = useChats();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const cancelRenameRef = useRef(false);

  useEffect(() => {
    if (!editingId) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [editingId]);

  const sorted = [...chats].sort(
    (left, right) => right.updatedAt - left.updatedAt,
  );
  const timeFormatter = new Intl.DateTimeFormat(
    lang === "en" ? "en-GB" : "ru-RU",
    { hour: "2-digit", minute: "2-digit" },
  );
  const dateFormatter = new Intl.DateTimeFormat(
    lang === "en" ? "en-GB" : "ru-RU",
    { day: "2-digit", month: "2-digit" },
  );
  const formatChatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toDateString() === new Date().toDateString()
      ? timeFormatter.format(date)
      : dateFormatter.format(date);
  };

  const handleNewChat = () => {
    newChat();
    onClose();
  };

  const handleSwitch = (id: string) => {
    switchChat(id);
    onClose();
  };

  const handleDelete = (
    event: React.MouseEvent<HTMLButtonElement>,
    id: string,
  ) => {
    event.stopPropagation();
    if (window.confirm(t.deleteChatConfirm)) deleteChat(id);
  };

  const startRename = (
    event: React.MouseEvent<HTMLButtonElement>,
    id: string,
    title: string,
  ) => {
    event.stopPropagation();
    cancelRenameRef.current = false;
    setDraftTitle(title);
    setEditingId(id);
  };

  const commitRename = (id: string, currentTitle: string) => {
    if (cancelRenameRef.current) {
      cancelRenameRef.current = false;
      setEditingId(null);
      return;
    }
    const value = draftTitle.replace(/\s+/g, " ").trim();
    if (value && value !== currentTitle) renameChat(id, value);
    setEditingId(null);
  };

  return (
    <>
      {open ? (
        <div
          className="app-overlay fixed inset-0 z-40 lg:hidden"
          aria-hidden="true"
          onClick={onClose}
        />
      ) : null}

      <aside
        aria-label={t.chats}
        className={`app-surface app-border fixed inset-y-0 left-0 z-50 flex w-72 shrink-0 flex-col border-r transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0 ${
          open
            ? "visible translate-x-0"
            : "invisible -translate-x-full pointer-events-none lg:visible lg:pointer-events-auto"
        }`}
      >
        <div className="flex items-center justify-between border-b app-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="app-accent-gradient app-round-sm flex h-8 w-8 shrink-0 items-center justify-center text-xs font-bold">
              {t.assistantInitial}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold app-text">
                {t.chats}
              </div>
              <div className="truncate text-[0.65rem] app-muted">
                {t.chatsHint}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.closeChats}
            title={t.closeChats}
            className="app-muted app-hover-surface app-hover-text flex h-8 w-8 items-center justify-center rounded-lg transition lg:hidden"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="px-3 py-3">
          <button
            type="button"
            onClick={handleNewChat}
            className="app-primary app-round-sm flex w-full items-center justify-center gap-2 px-3 py-2 text-sm font-medium transition"
          >
            <PlusIcon />
            {t.newChat}
          </button>
        </div>

        <div className="aui-scrollbar min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {!ready ? (
            <div className="px-2 py-6 text-center text-xs app-muted">
              {t.loadingChats}
            </div>
          ) : sorted.length === 0 ? (
            <div className="px-2 py-6 text-center text-xs app-muted">
              {t.noChats}
            </div>
          ) : (
            <ul className="space-y-1">
              {sorted.map((chat) => {
                const active = chat.id === activeId;
                const preview = chat.messages.at(-1)?.text ?? "";
                const editing = editingId === chat.id;
                return (
                  <li key={chat.id}>
                    <div
                      className={`group flex items-start gap-1 border app-round-sm px-2 py-2 transition ${
                        active
                          ? "app-accent-soft"
                          : "border-transparent app-hover-surface"
                      }`}
                    >
                      {editing ? (
                        <div className="min-w-0 flex-1">
                          <input
                            ref={inputRef}
                            value={draftTitle}
                            maxLength={160}
                            aria-label={t.renameChatHint}
                            placeholder={t.renameChatPlaceholder}
                            onChange={(event) => setDraftTitle(event.target.value)}
                            onBlur={() => commitRename(chat.id, chat.title)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                event.currentTarget.blur();
                              } else if (event.key === "Escape") {
                                event.preventDefault();
                                cancelRenameRef.current = true;
                                event.currentTarget.blur();
                              }
                            }}
                            className="app-surface app-text app-round-xs w-full border app-border px-2 py-1 text-xs outline-none"
                          />
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleSwitch(chat.id)}
                          aria-current={active ? "true" : undefined}
                          className="min-w-0 flex-1 text-left"
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`truncate text-xs font-medium ${
                                active ? "app-accent-text" : "app-text"
                              }`}
                            >
                              {chat.title || t.newChat}
                            </span>
                            <span className="ml-auto shrink-0 text-[0.6rem] app-muted-2">
                              {formatChatTime(chat.updatedAt)}
                            </span>
                          </div>
                          {preview ? (
                            <div className="mt-0.5 line-clamp-1 text-[0.65rem] app-muted">
                              {preview}
                            </div>
                          ) : null}
                        </button>
                      )}
                      {!editing ? (
                        <button
                          type="button"
                          onClick={(event) =>
                            startRename(event, chat.id, chat.title)
                          }
                          aria-label={t.renameChat}
                          title={t.renameChat}
                          className="app-muted-2 app-hover-text mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md opacity-60 transition hover:text-[color:var(--accent)] focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
                        >
                          <PencilIcon />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={(event) => handleDelete(event, chat.id)}
                        aria-label={t.deleteChat}
                        title={t.deleteChat}
                        className="app-muted-2 app-hover-text mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md opacity-60 transition hover:text-rose-500 focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="space-y-2 border-t app-border px-3 py-3">
          <button
            type="button"
            onClick={onSettings}
            className="app-muted app-hover-surface app-hover-text flex w-full items-center gap-2 app-round-sm px-2 py-2 text-xs font-medium transition"
          >
            <GearIcon />
            {t.settings}
          </button>
          <p className="px-1 text-[0.62rem] leading-relaxed app-muted-2">
            {t.chatsStoredLocally}
          </p>
        </div>
      </aside>
    </>
  );
}
