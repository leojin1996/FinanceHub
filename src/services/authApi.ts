export interface UserInfo {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

const TOKEN_KEY = "financehub.token";

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // storage unavailable — token only lives in memory for this session
  }
}

export function clearStoredToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/**
 * Drop-in replacement for `fetch` that injects the JWT Authorization header.
 * On 401, clears the stored token so the app redirects to login.
 */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getStoredToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    clearStoredToken();
  }
  return response;
}

/** FastAPI may return `detail` as a string, object, or validation error array. */
export function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item && typeof (item as { msg: unknown }).msg === "string") {
          return (item as { msg: string }).msg;
        }
        return null;
      })
      .filter(Boolean) as string[];
    if (parts.length > 0) {
      return parts.join("；");
    }
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof (detail as { message: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  return "";
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const fromDetail = formatApiErrorDetail(payload?.detail);
    const message = fromDetail || `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await readJson<AuthResponse>(res);
  storeToken(data.access_token);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await readJson<AuthResponse>(res);
  storeToken(data.access_token);
  return data;
}

export async function fetchMe(): Promise<UserInfo> {
  const res = await authFetch("/api/auth/me");
  return readJson<UserInfo>(res);
}
