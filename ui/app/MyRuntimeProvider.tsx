"use client";

import { AssistantRuntimeProvider } from "@assistant-ui/react";
import {
  unstable_createLangGraphStream,
  useLangGraphRuntime,
  type LangChainMessage,
} from "@assistant-ui/react-langgraph";
import { Client } from "@langchain/langgraph-sdk";
import { useMemo } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ??
  (typeof window !== "undefined" ? "/api" : "http://127.0.0.1:2024");
const ASSISTANT_ID =
  process.env.NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID ?? "audit_assistant";

export function MyRuntimeProvider({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const client = useMemo(() => new Client({ apiUrl: API_URL }), []);

  const runtime = useLangGraphRuntime({
    stream: unstable_createLangGraphStream({
      client,
      assistantId: ASSISTANT_ID,
    }),
    create: async () => {
      const thread = await client.threads.create();
      return { externalId: thread.thread_id };
    },
    load: async (externalId: string) => {
      const state = await client.threads.getState(externalId);
      const messages =
        (state.values as { messages?: LangChainMessage[] })?.messages ?? [];
      return { messages, interrupts: [] };
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
