// Every request goes through `api()`. It adds the access token, and on a 401 it refreshes
// the tokens once (shared by concurrent requests) and retries; if that fails the user is
// logged out.

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const BASE = `${API_URL}/api/v1`;

const ACCESS_KEY = "dm.access_token";
const REFRESH_KEY = "dm.refresh_token";

export type TokenPair = { access_token: string; refresh_token: string };

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export const tokens = {
  get access() {
    return read(ACCESS_KEY);
  },
  get refresh() {
    return read(REFRESH_KEY);
  },
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

type Listener = () => void;
const logoutListeners = new Set<Listener>();

/** Called when the session can't be recovered (refresh failed). */
export function onSessionExpired(fn: Listener): () => void {
  logoutListeners.add(fn);
  return () => logoutListeners.delete(fn);
}

export type FieldErrors = Record<string, string>;

export class ApiError extends Error {
  /** 0 means the request never reached the server. */
  status: number;
  /** Ready to show — set when the server sent a string `detail`. */
  detail: string | null;
  /** From FastAPI's automatic 422 list: field name → English validator message. */
  fields: FieldErrors;

  constructor(status: number, detail: string | null, fields: FieldErrors = {}) {
    super(detail ?? `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
    this.fields = fields;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  query?: Query;
  /** false for login/register/refresh */
  auth?: boolean;
  signal?: AbortSignal;
};

export function apiUrl(path: string, query?: Query): string {
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.toString();
}

async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON error (proxy page, etc.)
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new ApiError(res.status, detail);
  if (Array.isArray(detail)) {
    const fields: FieldErrors = {};
    for (const item of detail as { loc?: unknown[]; msg?: string }[]) {
      const loc = item.loc ?? [];
      const name = String(loc[loc.length - 1] ?? "");
      if (name && !fields[name]) fields[name] = item.msg ?? "";
    }
    return new ApiError(res.status, null, fields);
  }
  return new ApiError(res.status, null);
}

async function send(path: string, opts: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    return await fetch(apiUrl(path, opts.query), {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, null);
  }
}

let refreshing: Promise<boolean> | null = null;

function refreshTokens(): Promise<boolean> {
  // Several requests may get a 401 at once; they all wait on the same refresh.
  refreshing ??= (async () => {
    const refresh = tokens.refresh;
    if (!refresh) return false;
    try {
      const res = await send("/auth/refresh", { method: "POST", json: { refresh_token: refresh } }, null);
      if (!res.ok) return false;
      tokens.set((await res.json()) as TokenPair);
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function expireSession() {
  tokens.clear();
  logoutListeners.forEach((fn) => fn());
}

export async function api<T = void>(path: string, opts: RequestOptions = {}): Promise<T> {
  const auth = opts.auth ?? true;
  let res = await send(path, opts, auth ? tokens.access : null);

  if (res.status === 401 && auth) {
    if (await refreshTokens()) {
      res = await send(path, opts, tokens.access);
    }
    if (res.status === 401) {
      expireSession();
      throw await parseError(res);
    }
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
