import type { AuthResponse, User } from './types';

const TOKEN_KEY = 'regtrack.token';
const USER_KEY = 'regtrack.user';

function normalizeBase(value: string | undefined): string {
  if (!value || value.trim() === '') return 'http://localhost:8080';
  return value.trim().replace(/\/+$/, '');
}

export const API_BASE = normalizeBase(import.meta.env.VITE_API_BASE);

export const UNAUTHORIZED_EVENT = 'regtrack:unauthorized';

export class ApiError extends Error {
  readonly status: number;
  readonly fields?: Record<string, string>;

  constructor(status: number, message: string, fields?: Record<string, string>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fields = fields;
  }
}

export const tokenStore = {
  get(): string | null {
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string): void {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable — session stays in memory only */
    }
  },
  clear(): void {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
  },
};

export const userStore = {
  get(): User | null {
    try {
      const raw = window.localStorage.getItem(USER_KEY);
      return raw ? (JSON.parse(raw) as User) : null;
    } catch {
      return null;
    }
  },
  set(user: User): void {
    try {
      window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch {
      /* ignore */
    }
  },
  clear(): void {
    tokenStore.clear();
  },
};

function forceLogout(): void {
  tokenStore.clear();
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

function extractFields(payload: unknown): Record<string, string> | undefined {
  if (payload && typeof payload === 'object' && 'fields' in payload) {
    const fields = (payload as { fields?: unknown }).fields;
    if (fields && typeof fields === 'object') {
      const out: Record<string, string> = {};
      for (const [key, value] of Object.entries(fields as Record<string, unknown>)) {
        out[key] = value == null ? '' : String(value);
      }
      return out;
    }
  }
  return undefined;
}

function extractMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'message' in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim() !== '') return message;
  }
  return fallback;
}

export interface RequestOptions extends Omit<RequestInit, 'headers' | 'body'> {
  body?: unknown;
  headers?: Record<string, string>;
  /** Skip the global 401 → logout broadcast (used by the login call itself). */
  skipAuthRedirect?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers = {}, skipAuthRedirect = false, ...rest } = options;
  const requestHeaders: Record<string, string> = { Accept: 'application/json', ...headers };
  if (body !== undefined) requestHeaders['Content-Type'] = 'application/json';

  const token = tokenStore.get();
  if (token) requestHeaders.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${API_BASE}. Is the backend running?`,
    );
  }

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      if (!skipAuthRedirect) {
        forceLogout();
      }
      throw new ApiError(
        401,
        extractMessage(payload, 'Your session has expired. Please sign in again.'),
        extractFields(payload),
      );
    }
    throw new ApiError(
      response.status,
      extractMessage(payload, `Request failed with status ${response.status}`),
      extractFields(payload),
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiFetch<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: 'PATCH', body }),
  del: <T>(path: string, options?: RequestOptions) => apiFetch<T>(path, { ...options, method: 'DELETE' }),
};

export async function loginRequest(email: string, password: string): Promise<AuthResponse> {
  return api.post<AuthResponse>('/api/auth/login', { email, password }, { skipAuthRedirect: true });
}
