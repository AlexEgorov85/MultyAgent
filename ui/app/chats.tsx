"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  deleteBackendThread,
  deleteRemoteChat,
  renameRemoteChat,
} from "./dialogueAdmin";
import { readPreferences } from "./preferences";

export type TraceChip = {
  label: string;
  value: string;
};

export type TraceStep = {
  step: string;
  title: string;
  detail?: string;
  status?: string;
  agent?: string;
  kind?: string;
  code?: string;
  chips?: TraceChip[];
  duration_s?: number;
  route?: string;
  route_label?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  trace?: TraceStep[];
  createdAt: number;
};

export type Chat = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  backendThreadId: string | null;
  messages: ChatMessage[];
  running: boolean;
};

type ChatStore = {
  chats: Chat[];
  activeId: string | null;
};

type ChatContextValue = ChatStore & {
  activeChat: Chat | null;
  ready: boolean;
  newChat: () => Chat;
  switchChat: (id: string) => void;
  renameChat: (id: string, title: string) => void;
  deleteChat: (id: string) => void;
  appendMessage: (chatId: string, message: ChatMessage) => void;
  setBackendThreadId: (chatId: string, threadId: string) => void;
  setRunning: (chatId: string, running: boolean) => void;
};

const STORAGE_KEY = "audit-ui-chats-v1";
const MAX_CHATS = 40;
const MAX_MESSAGES = 300;

const ChatContext = createContext<ChatContextValue | null>(null);

export function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeChat(): Chat {
  const now = Date.now();
  return {
    id: newId(),
    title: "",
    createdAt: now,
    updatedAt: now,
    backendThreadId: null,
    messages: [],
    running: false,
  };
}

function titleFromText(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 64
    ? `${normalized.slice(0, 61).trimEnd()}…`
    : normalized;
}

function asTimestamp(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function sanitizeTrace(value: unknown): TraceStep[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const steps = value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const step = item as Partial<TraceStep>;
      if (typeof step.title !== "string" || !step.title.trim()) return null;
      const chips = Array.isArray(step.chips)
        ? step.chips
            .map((chip) => {
              if (!chip || typeof chip !== "object") return null;
              const { label, value } = chip as Partial<TraceChip>;
              if (typeof label !== "string" || typeof value !== "string") {
                return null;
              }
              return { label, value };
            })
            .filter((chip): chip is TraceChip => chip !== null)
            .slice(0, 8)
        : undefined;
      return {
        step: typeof step.step === "string" ? step.step : "step",
        title: step.title,
        ...(typeof step.detail === "string" ? { detail: step.detail } : {}),
        ...(typeof step.status === "string" ? { status: step.status } : {}),
        ...(typeof step.agent === "string" ? { agent: step.agent } : {}),
        ...(typeof step.kind === "string" ? { kind: step.kind } : {}),
        ...(typeof step.code === "string" ? { code: step.code } : {}),
        ...(chips && chips.length > 0 ? { chips } : {}),
        ...(typeof step.duration_s === "number" &&
        Number.isFinite(step.duration_s)
          ? { duration_s: step.duration_s }
          : {}),
        ...(typeof step.route === "string" ? { route: step.route } : {}),
        ...(typeof step.route_label === "string"
          ? { route_label: step.route_label }
          : {}),
      } satisfies TraceStep;
    })
    .filter((item): item is TraceStep => item !== null);
  return steps.length > 0 ? steps.slice(0, 40) : undefined;
}

function sanitizeMessage(value: unknown): ChatMessage | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<ChatMessage>;
  if (
    typeof raw.id !== "string" ||
    !raw.id ||
    (raw.role !== "user" && raw.role !== "assistant") ||
    typeof raw.text !== "string"
  ) {
    return null;
  }
  const trace = sanitizeTrace(raw.trace);
  return {
    id: raw.id,
    role: raw.role,
    text: raw.text,
    createdAt: asTimestamp(raw.createdAt, Date.now()),
    ...(trace ? { trace } : {}),
  };
}

function sanitizeChat(value: unknown): Chat | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<Chat>;
  if (typeof raw.id !== "string" || !raw.id) return null;
  const now = Date.now();
  const messages = Array.isArray(raw.messages)
    ? raw.messages
        .map(sanitizeMessage)
        .filter((item): item is ChatMessage => item !== null)
        .slice(-MAX_MESSAGES)
    : [];
  return {
    id: raw.id,
    title: typeof raw.title === "string" ? raw.title.slice(0, 160) : "",
    createdAt: asTimestamp(raw.createdAt, now),
    updatedAt: asTimestamp(raw.updatedAt, now),
    backendThreadId:
      typeof raw.backendThreadId === "string" && raw.backendThreadId
        ? raw.backendThreadId
        : null,
    messages,
    running: false,
  };
}

function readChatStore(): ChatStore {
  if (typeof window === "undefined") return { chats: [], activeId: null };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw
      ? (JSON.parse(raw) as { chats?: unknown; activeId?: unknown })
      : {};
    const chats = Array.isArray(parsed.chats)
      ? parsed.chats
          .map(sanitizeChat)
          .filter((item): item is Chat => item !== null)
          .slice(0, MAX_CHATS)
      : [];
    if (chats.length === 0) {
      const chat = makeChat();
      return { chats: [chat], activeId: chat.id };
    }
    const activeId =
      typeof parsed.activeId === "string" &&
      chats.some((chat) => chat.id === parsed.activeId)
        ? parsed.activeId
        : chats[0].id;
    return { chats, activeId };
  } catch {
    const chat = makeChat();
    return { chats: [chat], activeId: chat.id };
  }
}

function writeChatStore(chats: Chat[], activeId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const payload = {
      activeId,
      chats: chats.map(({ running: _running, ...chat }) => chat),
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Переполнение localStorage не должно ломать интерфейс.
  }
}

export function ChatsProvider({ children }: { children: ReactNode }) {
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readChatStore();
    setChats(stored.chats);
    setActiveId(stored.activeId);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    writeChatStore(chats, activeId);
  }, [chats, activeId, ready]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) return;
      const stored = readChatStore();
      setChats(stored.chats);
      setActiveId(stored.activeId);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const newChat = useCallback(() => {
    const chat = makeChat();
    setChats((previous) => [chat, ...previous].slice(0, MAX_CHATS));
    setActiveId(chat.id);
    return chat;
  }, []);

  const switchChat = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const renameChat = useCallback(
    (id: string, title: string) => {
      const value = title.replace(/\s+/g, " ").trim().slice(0, 160);
      if (!value) return;
      setChats((previous) =>
        previous.map((chat) =>
          chat.id === id
            ? { ...chat, title: value, updatedAt: Date.now() }
            : chat,
        ),
      );
      const { auditorId } = readPreferences();
      void renameRemoteChat(id, value, auditorId).catch((error) => {
        console.warn("Не удалось переименовать чат в БД:", error);
      });
    },
    [],
  );

  const deleteChat = useCallback(
    (id: string) => {
      const target = chats.find((chat) => chat.id === id);
      const remaining = chats.filter((chat) => chat.id !== id);
      if (remaining.length === 0) {
        const chat = makeChat();
        setChats([chat]);
        setActiveId(chat.id);
      } else {
        setChats(remaining);
        if (activeId === id) {
          const next = [...remaining].sort(
            (left, right) => right.updatedAt - left.updatedAt,
          )[0];
          setActiveId(next.id);
        }
      }

      if (target) {
        const { auditorId } = readPreferences();
        void deleteRemoteChat(target.id, auditorId).catch((error) => {
          console.warn("Не удалось удалить чат из БД:", error);
        });
        void deleteBackendThread(target.backendThreadId).catch((error) => {
          console.warn("Не удалось удалить thread backend:", error);
        });
      }
    },
    [chats, activeId],
  );

  const appendMessage = useCallback((chatId: string, message: ChatMessage) => {
    setChats((previous) =>
      previous.map((chat) => {
        if (chat.id !== chatId) return chat;
        const title =
          chat.title ||
          (message.role === "user" ? titleFromText(message.text) : chat.title);
        return {
          ...chat,
          title,
          updatedAt: Date.now(),
          messages: [...chat.messages, message].slice(-MAX_MESSAGES),
        };
      }),
    );
  }, []);

  const setBackendThreadId = useCallback(
    (chatId: string, threadId: string) => {
      setChats((previous) =>
        previous.map((chat) =>
          chat.id === chatId
            ? { ...chat, backendThreadId: threadId, updatedAt: Date.now() }
            : chat,
        ),
      );
    },
    [],
  );

  const setRunning = useCallback((chatId: string, running: boolean) => {
    setChats((previous) =>
      previous.map((chat) =>
        chat.id === chatId ? { ...chat, running } : chat,
      ),
    );
  }, []);

  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === activeId) ?? chats[0] ?? null,
    [chats, activeId],
  );

  const value = useMemo<ChatContextValue>(
    () => ({
      chats,
      activeId,
      activeChat,
      ready,
      newChat,
      switchChat,
      renameChat,
      deleteChat,
      appendMessage,
      setBackendThreadId,
      setRunning,
    }),
    [
      chats,
      activeId,
      activeChat,
      ready,
      newChat,
      switchChat,
      renameChat,
      deleteChat,
      appendMessage,
      setBackendThreadId,
      setRunning,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChats(): ChatContextValue {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChats must be used inside ChatsProvider");
  }
  return context;
}
