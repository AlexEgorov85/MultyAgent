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
      <h1 className="text-2xl font-semibold tracking-tight app-text">
        Что-то пошло не так
      </h1>
      <p className="mt-1 text-sm app-muted">Something went wrong</p>
      <p className="mt-3 max-w-md text-xs leading-relaxed app-muted-2">
        Проверьте, что LangGraph API запущен, и повторите запрос. · Make sure the
        LangGraph API is running and try again.
      </p>
      {error.digest ? (
        <p className="mt-2 text-[0.65rem] app-muted-2">
          digest: {error.digest}
        </p>
      ) : null}
      <div className="mt-6 flex items-center gap-2">
        <button
          type="button"
          onClick={reset}
          className="app-primary app-round-sm px-4 py-2 text-sm font-medium transition"
        >
          Повторить · Retry
        </button>
        <a
          href="/"
          className="app-surface app-border app-text app-round-sm border px-4 py-2 text-sm font-medium transition app-accent-hover"
        >
          В чат · Back to chat
        </a>
      </div>
    </main>
  );
}
