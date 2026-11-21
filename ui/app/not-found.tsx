import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl font-bold text-white shadow-lg">
        404
      </div>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Страница не найдена
      </h1>
      <p className="mt-1 text-sm text-slate-500">Page not found</p>
      <Link
        href="/"
        className="mt-6 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
      >
        Вернуться в чат · Back to chat
      </Link>
    </main>
  );
}
