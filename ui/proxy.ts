import { timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

const USER = process.env.SHARE_BASIC_AUTH_USER ?? "demo";
const PASSWORD = process.env.SHARE_BASIC_AUTH_PASSWORD ?? "";

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

// Необязательный пароль для публичной ссылки. Включается переменной
// SHARE_BASIC_AUTH_PASSWORD в ui/.env.local (см. docs/share_ui.md).
// Без неё прокси ничего не меняет и работает как раньше.
export function proxy(request: NextRequest) {
  if (!PASSWORD) return NextResponse.next();

  const pair = readCredentials(request);
  if (pair && safeEqual(pair.user, USER) && safeEqual(pair.password, PASSWORD)) {
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
