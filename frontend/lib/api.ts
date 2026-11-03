/**
 * One fetch wrapper for the whole app.
 *  - sends cookies (JWT / session) with every call
 *  - adds the X-CSRFToken header on every state-changing request
 *  - user API: on 401 it calls /refresh/ once and retries the original request
 *  - turns Django's {"error": {code, message, fields}} into an ApiError
 */

export type Fields = Record<string, string[]>;

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Fields;
  requestId?: string;
  constructor(status: number, code: string, message: string, fields: Fields = {}, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.requestId = requestId;
  }
}

export type AuthKind = "user" | "admin" | "none";

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: AuthKind;
};

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

/** Make sure the csrftoken cookie exists. Pass force=true after login (Django rotates it). */
export async function ensureCsrf(force = false) {
  if (!force && getCookie("csrftoken")) return;
  await fetch("/api/csrf/", { credentials: "same-origin" });
}

// ---- token timing (display only): the cookies are HttpOnly, so we note when we saw a login/refresh
const TOKEN_KEY = "hp_token_issued_at";
export const ACCESS_MINUTES = 15;

export function markTokenIssued() {
  try {
    sessionStorage.setItem(TOKEN_KEY, String(Date.now()));
  } catch {}
}
export function minutesUntilRenewal(): number | null {
  try {
    const at = Number(sessionStorage.getItem(TOKEN_KEY));
    if (!at) return null;
    const left = ACCESS_MINUTES - (Date.now() - at) / 60000;
    return Math.max(0, Math.ceil(left));
  } catch {
    return null;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  type ErrorBody = { error?: { code?: string; message?: string; fields?: Fields; request_id?: string } };
  let body: ErrorBody | null = null;
  try {
    body = (await res.json()) as ErrorBody;
  } catch {}
  const err = body?.error;
  return new ApiError(
    res.status,
    err?.code ?? "error",
    err?.message ?? `Request failed (${res.status})`,
    err?.fields ?? {},
    err?.request_id ?? res.headers.get("X-Request-ID") ?? undefined
  );
}

let refreshing: Promise<boolean> | null = null;
function refreshSession(): Promise<boolean> {
  // single-flight: many parallel 401s trigger only one refresh call
  if (!refreshing) {
    refreshing = (async () => {
      try {
        await ensureCsrf();
        const res = await fetch("/api/auth/user/refresh/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
        });
        if (res.ok) markTokenIssued();
        return res.ok;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const auth = opts.auth ?? "user";

  const send = async () => {
    const headers: Record<string, string> = {};
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (!SAFE.has(method)) {
      await ensureCsrf();
      headers["X-CSRFToken"] = getCookie("csrftoken") ?? "";
    }
    return fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  };

  let res = await send();

  // expired access token -> refresh once, retry once (user API only)
  if (res.status === 401 && auth === "user" && !path.startsWith("/auth/user/")) {
    if (await refreshSession()) res = await send();
  }

  // stale CSRF token (e.g. after login) -> fetch a fresh one, retry once
  if (res.status === 403 && !SAFE.has(method)) {
    const clone = res.clone();
    const body = await clone.json().catch(() => null);
    if (String(body?.error?.message ?? "").includes("CSRF")) {
      await ensureCsrf(true);
      res = await send();
    }
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ------------------------------------------------------------------ types
export type User = { id: number; name: string; email: string; role: "user" | "admin"; date_joined: string };

// ---- member profile (all sections, full data: members see their own everything)
export type Demographics = {
  full_name: string;
  preferred_name: string;
  date_of_birth: string | null;
  age_range: string | null;
  gender: string;
  city: string;
  created_at?: string;
};

export type EmergencyContact = {
  id: number;
  name: string;
  relationship: string;
  phone: string;
  is_primary: boolean;
};

export type Wellness = {
  contact_preference: "email" | "phone" | "sms";
  activity_level: string;
  diet_preference: string;
  sleep_goal_hours: number | null;
  allergies: string;
  lifestyle_notes: string;
  goals: string[];
  created_at?: string;
};

export type Completion = {
  status: "not_started" | "in_progress" | "complete";
  percent: number;
  missing: string[];
};

export type Profile = {
  id: number;
  status: "active" | "deactivated";
  completion: Completion;
  demographics: Demographics | null;
  emergency_contacts: EmergencyContact[];
  wellness: Wellness | null;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: number;
  created_at: string;
  action: string;
  target_type: string;
  target_id: number | null;
  changed_fields: string[];
  outcome: "success" | "denied" | "failed";
  request_id: string | null;
};

// ---- admin views (an allow-list: no date of birth, allergies, notes or full phone numbers)
export type AdminAuditEvent = AuditEvent & { actor: number | null; actor_role: string };

export type AdminRow = {
  id: number;
  display_name: string;
  email: string;
  status: "active" | "deactivated";
  completion_status: Completion["status"];
  completion_percent: number;
  created_at: string;
};

export type AdminProfile = AdminRow & {
  updated_at: string;
  demographics: {
    full_name: string;
    preferred_name: string;
    age_range: string | null;
    gender: string;
    city: string;
  } | null;
  emergency_contacts: { id: number; name: string; relationship: string; phone_masked: string; is_primary: boolean }[];
  wellness: {
    contact_preference: string;
    activity_level: string;
    diet_preference: string;
    sleep_goal_hours: number | null;
    goals: string[];
    has_allergies: boolean;
  } | null;
};
export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

// ------------------------------------------------------------------ user auth helpers
export async function userLogin(email: string, password: string) {
  const user = await api<User>("/auth/user/login/", { method: "POST", body: { email, password }, auth: "none" });
  markTokenIssued();
  await ensureCsrf(true); // login rotates the CSRF token
  return user;
}

export async function userSignup(name: string, email: string, password: string) {
  return api<User>("/auth/signup/", { method: "POST", body: { name, email, password }, auth: "none" });
}

export async function userLogout() {
  try {
    await api("/auth/user/logout/", { method: "POST", auth: "none" });
  } finally {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {}
  }
}

export async function adminLogin(email: string, password: string) {
  await ensureCsrf(true);
  const user = await api<User>("/admin/login/", { method: "POST", body: { email, password }, auth: "admin" });
  await ensureCsrf(true); // login rotates the CSRF token
  return user;
}

export async function adminLogout() {
  await api("/admin/logout/", { method: "POST", auth: "admin" });
}

export function fieldError(err: unknown, field: string): string | undefined {
  return err instanceof ApiError ? err.fields[field]?.[0] : undefined;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const first = Object.values(err.fields)[0]?.[0];
    if (err.status === 400 && first) return first;
    // Quote the request id so a problem can be traced to the matching audit / server log line.
    return err.requestId ? `${err.message} (ref ${err.requestId.slice(0, 8)})` : err.message;
  }
  return "Something went wrong. Please try again.";
}
