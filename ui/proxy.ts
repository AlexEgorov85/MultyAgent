import { timingSafeEqual } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse, type NextRequest } from "next/server";

// Пароль можно включать и выключать тремя способами (по приоритету):
//   1. ui/.share-auth.json      — горячо, без перезапуска (см. scripts/share_auth.ps1);
//   2. SHARE_AUTH_ENABLED=on|off — на один запуск UI (флаг -NoAuth у share_ui.ps1);
//   3. SHARE_BASIC_AUTH_PASSWORD — постоянная настройка в ui/.env.local (пусто = выключено).
const AUTH_FILE =
  process.env.SHARE_AUTH_FILE ?? path.join(process.cwd(), ".share-auth.json");
const DEFAULT_USER = process.env.SHARE_BASIC_AUTH_USER ?? "demo";
const DEFAULT_PASSWORD = process.env.SHARE_BASIC_AUTH_PASSWORD ?? "";
const ENV_SWITCH = (process.env.SHARE_AUTH_ENABLED ?? "").trim().toLowerCase();

type AuthState = { enabled: boolean; user: string; password: string };

function envDefaultEnabled(): boolean {
  if (["off", "0", "false", "no"].includes(ENV_SWITCH)) return false;
  if (["on", "1", "true", "yes"].includes(ENV_SWITCH)) return true;
  return DEFAULT_PASSWORD.length > 0;
}

async function readFileState(): Promise<Partial<AuthState> | null> {
  try {
    // Путь задаётся в рантайме (SHARE_AUTH_FILE или cwd), поэтому без
    // turbopackIgnore сборщик трассирует весь проект. Файл читается только
    // при обработке запроса, в бандл он не нужен.
    const parsed = JSON.parse(
      await readFile(/* turbopackIgnore: true */ AUTH_FILE, "utf8"),
    ) as Partial<AuthState>;
    if (typeof parsed?.enabled !== "boolean") return null;
    return parsed;
  } catch {
    // Файла нет или он битый — работаем по настройкам окружения.
    return null;
  }
}

async function resolveAuth(): Promise<AuthState> {
  const file = await readFileState();
  return {
    enabled: file?.enabled ?? envDefaultEnabled(),
    user: file?.user ?? DEFAULT_USER,
    password: file?.password ?? DEFAULT_PASSWORD,
  };
}

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

function readCredentials(
  request: NextRequest,
): { user: string; password: string } | null {
  const header = request.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) return null;
  let decoded: string;
  try {
    decoded = Buffer.from(header.slice("Basic ".length), "base64").toString(
      "utf8",
    );
  } catch {
    return null;
  }
  const separator = decoded.indexOf(":");
  if (separator < 0) return null;
  return {
    user: decoded.slice(0, separator),
    password: decoded.slice(separator + 1),
  };
}

export async function proxy(request: NextRequest) {
  const auth = await resolveAuth();
  if (!auth.enabled) return NextResponse.next();

  if (!auth.password) {
    return new NextResponse(
      "Пароль включён, но не задан: добавьте SHARE_BASIC_AUTH_PASSWORD в ui/.env.local.",
      {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
      },
    );
  }

  const pair = readCredentials(request);
  if (pair && safeEqual(pair.user, auth.user) && safeEqual(pair.password, auth.password)) {
    return NextResponse.next();
  }

  return new NextResponse("Требуется пароль для доступа к демо.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="audit-assistant", charset="UTF-8"',
      "Cache-Control": "no-store",
    },
  });
}

export const config = {
  // Пароль не нужен для статики Next: она не содержит данных и секретов.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
