"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-rose-600 text-2xl font-bold text-white shadow-lg">
        !
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Что-то пошло не так
      </h1>
      <p className="mt-1 text-sm text-slate-500">Something went wrong</p>
      <p className="mt-3 max-w-md text-xs leading-relaxed text-slate-400">
        Проверьте, что LangGraph API запущен, и повторите запрос. · Make sure the
        LangGraph API is running and try again.
      </p>
      {error.digest ? (
        <p className="mt-2 text-[0.65rem] text-slate-300">
          digest: {error.digest}
        </p>
      ) : null}
      <div className="mt-6 flex items-center gap-2">
        <button
          type="button"
          onClick={reset}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
        >
          Повторить · Retry
        </button>
        <a
          href="/"
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700"
        >
          В чат · Back to chat
        </a>
      </div>
    </main>
  );
}
