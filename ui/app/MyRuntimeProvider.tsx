"use client";

import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { useCallback, useRef, useState } from "react";
import { readPreferences } from "./preferences";

const API_BASE =
  process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://127.0.0.1:2024";
const ASSISTANT_ID =
  process.env.NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID ?? "audit_assistant";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  trace?: TraceStep[];
};

type TraceStep = {
  step: string;
  title: string;
  detail?: string;
  status?: string;
};

type ContentPart = { type?: string; text?: string };

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function textOf(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) =>
      part && typeof part === "object" && (part as ContentPart).type === "text"
        ? String((part as ContentPart).text ?? "")
        : "",
    )
    .join("")
    .trim();
}

function answerFromState(state: unknown): string {
  if (!state || typeof state !== "object") return "";
  const finalAnswer = (state as { final_answer?: unknown }).final_answer;
  if (typeof finalAnswer === "string" && finalAnswer.trim()) {
    return finalAnswer.trim();
  }
  const messages = (state as { messages?: unknown }).messages;
  if (!Array.isArray(messages)) return "";
  for (const message of [...messages].reverse()) {
    if (!message || typeof message !== "object") continue;
    const type = (message as { type?: string; role?: string }).type;
    const role = (message as { role?: string }).role;
    if (type === "ai" || type === "assistant" || role === "assistant") {
      const text = textOf((message as { content?: unknown }).content);
      if (text) return text;
    }
  }
  return "";
}

async function createThread(language: string): Promise<string> {
  const response = await fetch(`${API_BASE}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    throw new Error(
      language === "en"
        ? `could not create a thread (${response.status})`
        : `не удалось создать нить (${response.status})`,
    );
  }
  const body = (await response.json()) as { thread_id?: string };
  if (!body.thread_id) {
    throw new Error(
      language === "en"
        ? "the server did not return thread_id"
        : "сервер не вернул thread_id",
    );
  }
  return body.thread_id;
}

export function MyRuntimeProvider({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const threadId = useRef<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const convertMessage = useCallback(
    (message: ChatMessage): ThreadMessageLike => ({
      id: message.id,
      role: message.role,
      content: [{ type: "text", text: message.text }],
      metadata:
        message.trace && message.trace.length > 0
          ? { custom: { trace: message.trace } }
          : undefined,
    }),
    [],
  );

  const onNew = useCallback(async (message: AppendMessage) => {
    const { language, auditorId } = readPreferences();
    const ru = language !== "en";
    const question = textOf(message.content);
    if (!question) return;

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", text: question },
    ]);
    setIsRunning(true);

    let answer: string;
    let trace: TraceStep[] = [];
    try {
      threadId.current ??= await createThread(language);
      const waitUrl = `${API_BASE}/threads/${threadId.current}/runs/wait`;
      const response = await fetch(
        waitUrl,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            assistant_id: ASSISTANT_ID,
            input: {
              messages: [{ type: "human", content: question }],
              language,
              auditor_id: auditorId,
            },
          }),
        },
      );

      if (!response.ok) {
        answer = ru
          ? `Ошибка API: ${response.status} ${response.statusText}`
          : `API error: ${response.status} ${response.statusText}`;
      } else {
        const state = await response.json();
        answer =
          answerFromState(state) ||
          (ru
            ? "Не удалось получить ответ от агента."
            : "The agent did not return an answer.");
        trace = Array.isArray(state?.trace) ? (state.trace as TraceStep[]) : [];
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      answer = `${ru ? "Ошибка" : "Error"}: ${detail}`;
    } finally {
      setIsRunning(false);
    }

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "assistant", text: answer, trace },
    ]);
  }, []);

  const runtime = useExternalStoreRuntime<ChatMessage>({
    messages,
    isRunning,
    onNew,
    convertMessage,
    adapters: {
      threadList: {
        onSwitchToNewThread: async () => {
          setMessages([]);
          threadId.current = null;
        },
      },
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
