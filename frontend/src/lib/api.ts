import type { GameState } from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "questforge_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    return JSON.stringify(data.detail ?? data);
  } catch {
    return res.statusText || "Request failed";
  }
}

export async function register(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.access_token as string;
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.access_token as string;
}

export async function getCurrentGame(): Promise<GameState | null> {
  const res = await fetch(`${API_URL}/games/current`, {
    headers: { ...authHeaders() },
  });
  if (res.status === 404) return null;
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as GameState;
}

export async function newGame(): Promise<GameState> {
  const res = await fetch(`${API_URL}/games`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as GameState;
}

export async function resetGame(): Promise<GameState> {
  const res = await fetch(`${API_URL}/games/current`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as GameState;
}

export class UnauthorizedError extends Error {
  constructor() {
    super("Unauthorized");
    this.name = "UnauthorizedError";
  }
}

export interface ActionStreamHandlers {
  onToken?: (text: string) => void;
  onTool?: (record: Record<string, unknown>) => void;
  onDone?: (data: Record<string, unknown>) => void;
  onError?: (message: string) => void;
}

/**
 * POST a free-text action and consume the Server-Sent-Events stream.
 * We use fetch + ReadableStream (not EventSource) because the endpoint is a
 * POST with an Authorization header, which EventSource cannot send.
 */
export async function streamAction(
  action: string,
  handlers: ActionStreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_URL}/games/current/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ action }),
  });

  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok || !res.body) {
    throw new Error(await parseError(res));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const lines = frame.split("\n");
      let event = "message";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (!dataStr) continue;

      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataStr);
      } catch {
        continue;
      }

      switch (event) {
        case "token":
          handlers.onToken?.(String(data.text ?? ""));
          break;
        case "tool":
          handlers.onTool?.(data);
          break;
        case "done":
          handlers.onDone?.(data);
          break;
        case "error":
          handlers.onError?.(String(data.message ?? "AI error"));
          break;
        default:
          break;
      }
    }
  }
}
