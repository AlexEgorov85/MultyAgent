import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <div className="app-accent-gradient app-round mb-4 flex h-14 w-14 items-center justify-center text-2xl font-bold shadow-lg">
        404
      </div>
      <h1 className="text-2xl font-semibold tracking-tight app-text">
        Страница не найдена
      </h1>
      <p className="mt-1 text-sm app-muted">Page not found</p>
      <Link
        href="/"
        className="app-primary app-round-sm mt-6 px-4 py-2 text-sm font-medium transition"
      >
        Вернуться в чат · Back to chat
      </Link>
    </main>
  );
}
