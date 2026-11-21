"use client";

const API_BASE =
  process.env.NEXT_PUBLIC_LANGGRAPH_API_URL ?? "http://127.0.0.1:2024";
const ADMIN_ASSISTANT_ID =
  process.env.NEXT_PUBLIC_LANGGRAPH_ADMIN_ASSISTANT_ID ?? "dialogue_admin";

type AdminInput = {
  action: "rename" | "delete";
  conversation_id: string;
  title?: string;
  auditor_id?: string;
};

async function createThread(): Promise<string> {
  const response = await fetch(`${API_BASE}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    throw new Error(`admin thread: ${response.status}`);
  }
  const body = (await response.json()) as { thread_id?: string };
  if (!body.thread_id) throw new Error("admin thread: no thread_id");
  return body.thread_id;
}

async function deleteThread(threadId: string): Promise<void> {
  await fetch(`${API_BASE}/threads/${threadId}`, { method: "DELETE" });
}

async function runAdmin(input: AdminInput): Promise<void> {
  const threadId = await createThread();
  try {
    const response = await fetch(`${API_BASE}/threads/${threadId}/runs/wait`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assistant_id: ADMIN_ASSISTANT_ID,
        input,
      }),
    });
    if (!response.ok) {
      throw new Error(`admin run: ${response.status}`);
    }
    const body = (await response.json()) as { ok?: boolean; error?: string };
    if (body.ok === false) {
      throw new Error(body.error || "admin action failed");
    }
  } finally {
    await deleteThread(threadId).catch(() => undefined);
  }
}

export async function renameRemoteChat(
  conversationId: string,
  title: string,
  auditorId = "",
): Promise<void> {
  await runAdmin({
    action: "rename",
    conversation_id: conversationId,
    title,
    auditor_id: auditorId,
  });
}

export async function deleteRemoteChat(
  conversationId: string,
): Promise<void> {
  await runAdmin({ action: "delete", conversation_id: conversationId });
}

export async function deleteBackendThread(
  threadId: string | null | undefined,
): Promise<void> {
  if (!threadId) return;
  await deleteThread(threadId);
}
