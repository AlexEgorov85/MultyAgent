"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="ru">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f8fafc",
          color: "#0f172a",
          fontFamily:
            'Segoe UI, Inter, system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
          textAlign: "center",
          padding: "24px",
        }}
      >
        <main>
          <h1 style={{ margin: 0, fontSize: "24px" }}>
            Критическая ошибка
          </h1>
          <p style={{ marginTop: "8px", color: "#64748b", fontSize: "14px" }}>
            Critical error · Проверьте, что LangGraph API запущен.
          </p>
          {error.digest ? (
            <p style={{ marginTop: "8px", color: "#94a3b8", fontSize: "11px" }}>
              digest: {error.digest}
            </p>
          ) : null}
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: "24px",
              borderRadius: "12px",
              border: "none",
              background: "#0f172a",
              color: "#ffffff",
              padding: "10px 16px",
              fontSize: "14px",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Повторить · Retry
          </button>
        </main>
      </body>
    </html>
  );
}
