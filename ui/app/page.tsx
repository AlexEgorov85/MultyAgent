"use client";

import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";

const SUGGESTIONS = [
  {
    title: "Сколько проверок завершено?",
    text: "Сколько завершённых проверок по ипотеке в 2026 году?",
  },
  {
    title: "Найти похожие находки",
    text: "Найди отклонения про просроченную актуализацию оценки залога.",
  },
  {
    title: "Сформировать акт",
    text: "Сформируй раздел акта по AUD-2026-MORTGAGE-03.",
  },
  {
    title: "Почему выросла доля?",
    text: "Почему в ипотеке в 2026 году выросла доля просроченных пунктов?",
  },
];

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
  return (
    <MessagePrimitive.Root className="mr-auto max-w-[92%]">
      <div className="flex gap-3">
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-xs font-bold text-white shadow">
          А
        </div>
        <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-[0.95rem] leading-relaxed text-slate-800 shadow-sm">
          <div className="aui-text">
            <MessagePrimitive.Parts />
          </div>
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl text-white shadow-lg">
        А
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Ассистент внутреннего аудитора
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-500">
        Задайте вопрос по карманам, проверкам и находкам. Ассистент построит
        безопасный SQL, найдёт подтверждения в актах и подготовит проект раздела.
      </p>
      <div className="mt-7 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((item) => (
          <ThreadPrimitive.Suggestion
            key={item.title}
            prompt={item.text}
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

export default function Home() {
  return (
    <div className="flex h-dvh flex-col">
      <header className="border-b border-slate-200/70 bg-white/70 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white shadow">
            А
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900">
              Ассистент внутреннего аудитора
            </div>
            <div className="text-[0.7rem] text-slate-500">
              LangGraph · PostgreSQL · FIPA-ACL
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[0.7rem] font-medium text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            онлайн
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
            <ComposerPrimitive.Root className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100">
              <ComposerPrimitive.Input
                placeholder="Спросите про проверки, отклонения или акт…"
                rows={1}
                className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] text-slate-900 outline-none placeholder:text-slate-400"
              />
              <ComposerPrimitive.Send className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">
                Отправить
              </ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
            <div className="mt-2 text-center text-[0.68rem] text-slate-400">
              Ответы основаны только на данных аудиторской базы. Проверяйте
              критичные выводы по первоисточникам.
            </div>
          </div>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Root>
    </div>
  );
}
