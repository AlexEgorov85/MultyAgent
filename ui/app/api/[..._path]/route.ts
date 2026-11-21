import { type NextRequest, NextResponse } from "next/server";

const API_URL = (process.env.LANGGRAPH_API_URL ?? "http://127.0.0.1:2024").replace(
  /\/$/,
  "",
);

function isAllowedPath(path: string, method: string) {
  const thread = "[a-zA-Z0-9_-]+";
  if (method === "GET") {
    return (
      new RegExp(`^threads/${thread}/state$`).test(path) ||
      new RegExp(`^threads/${thread}/history$`).test(path) ||
      path === "assistants"
    );
  }
  if (method !== "POST") return false;
  return (
    path === "threads" ||
    path === "assistants/search" ||
    new RegExp(
      `^threads/${thread}/(?:commands|stream/events|history|runs/stream|runs/${thread}/cancel)$`,
    ).test(path)
  );
}

function isAllowedRequestContext(req: NextRequest) {
  const fetchSite = req.headers.get("sec-fetch-site");
  if (fetchSite !== null) {
    return fetchSite === "same-origin" || fetchSite === "none";
  }
  const origin = req.headers.get("origin");
  if (origin === null) return true;
  try {
    return new URL(origin).origin === req.nextUrl.origin;
  } catch {
    return false;
  }
}

function crossOriginResponse() {
  return NextResponse.json(
    { error: "Cross-origin requests are not allowed." },
    { status: 403 },
  );
}

async function handleRequest(req: NextRequest, method: string) {
  if (!isAllowedRequestContext(req)) return crossOriginResponse();

  const path = req.nextUrl.pathname.replace(/^\/?api\//, "");
  if (!isAllowedPath(path, method)) {
    return new NextResponse(null, { status: 404 });
  }

  const searchParams = new URLSearchParams(req.nextUrl.search);
  searchParams.delete("_path");
  searchParams.delete("nxtP_path");
  const query = searchParams.toString();

  const headers = new Headers();
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const options: RequestInit = {
    method,
    headers,
    redirect: "manual",
    signal: req.signal,
  };
  if (["POST", "PUT", "PATCH"].includes(method)) {
    options.body = await req.text();
  }

  try {
    const response = await fetch(
      `${API_URL}/${path}${query ? `?${query}` : ""}`,
      options,
    );
    const responseHeaders = new Headers(response.headers);
    for (const name of [
      "content-encoding",
      "content-length",
      "set-cookie",
      "transfer-encoding",
    ]) {
      responseHeaders.delete(name);
    }
    responseHeaders.set("Cache-Control", "no-store");
    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

export const GET = (req: NextRequest) => handleRequest(req, "GET");
export const HEAD = () => new NextResponse(null, { status: 404 });
export const POST = (req: NextRequest) => handleRequest(req, "POST");
export const PUT = () => new NextResponse(null, { status: 404 });
export const PATCH = () => new NextResponse(null, { status: 404 });
export const DELETE = () => new NextResponse(null, { status: 404 });
export const OPTIONS = (req: NextRequest) =>
  isAllowedRequestContext(req)
    ? new NextResponse(null, { status: 204 })
    : crossOriginResponse();
