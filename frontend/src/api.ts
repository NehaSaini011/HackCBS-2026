// Single API client for every screen.
//
// Two things decide what a screen is showing:
//
// 1. Mode, from VITE_USE_MOCKS (team contract):
//      mock  <=>  VITE_USE_MOCKS === "true"
//    Anything else (unset, empty, "false", a typo) means LIVE, so a missing or
//    unreadable env file surfaces as a real error instead of silently serving
//    fixtures.
//
// 2. In live mode, whether the real call worked. When the backend cannot answer at
//    all (unreachable, timed out, crashed, or the route does not exist yet) the
//    matching fixture in mock_for_now/ answers instead. A 4xx is a real answer —
//    bad credentials, a blocked approval, invalid input — and is never masked.
//
// Either way the app records where the body came from, so the UI can say "live" or
// "mock" and never let a fixture pass as a real result. A server may also mark its
// own responses with a `MOCK: true` response header, which is read here too.

import { hasFixture, mockForNow } from "./mockEngine";
import type {
  Finding,
  GroupOverview,
  Incident,
  Lesson,
  LoginResponse,
  MekoSetting,
  RiskRow,
  User,
  DecisionResponse,
  PushRiskResponse,
} from "./types";
import { FINAL_STATUSES } from "./types";

/** Response header a server may set to flag that its body is fixture data. */
export const MOCK_HEADER = "MOCK";

/** Trim and case-fold so " true ", "TRUE" or a stray BOM cannot flip the mode. */
export const USE_MOCKS: boolean =
  String(import.meta.env.VITE_USE_MOCKS ?? "")
    .replace(/^﻿/, "")
    .trim()
    .toLowerCase() === "true";

export const API_BASE: string = String(
  import.meta.env.VITE_API_URL || "http://localhost:8000",
)
  .replace(/^﻿/, "")
  .trim()
  .replace(/\/+$/, "");

const REQUEST_TIMEOUT_MS = 8000;
const NETWORK_ERROR =
  `Cannot reach the Group API at ${API_BASE}. Check that the backend is running ` +
  `and that its CORS settings allow this page.`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ---------- where the last body came from ----------
//   live     - the real API answered
//   mock     - mock mode, or the API answered with a MOCK:true header
//   fallback - the real API could not answer, so mock_for_now/ did
export type Source = "unknown" | "live" | "mock" | "fallback";

export interface Transport {
  path: string;
  method: string;
  source: Source;
  /** Why a fixture was used. Empty for a live answer. */
  reason: string;
  at: number;
}

let transport: Transport = {
  path: "",
  method: "",
  source: "unknown",
  reason: "",
  at: 0,
};
const transportListeners = new Set<(t: Transport) => void>();

function report(t: Omit<Transport, "at">) {
  transport = { ...t, at: Date.now() };
  transportListeners.forEach((fn) => fn(transport));
}

export const getTransport = () => transport;

export function subscribeTransport(fn: (t: Transport) => void) {
  transportListeners.add(fn);
  return () => {
    transportListeners.delete(fn);
  };
}

/**
 * Should a failed live call be answered from mock_for_now/?
 *
 * Only when the backend could not produce an answer: it was unreachable (0), it
 * crashed (5xx), or the route is not built yet (404). A 4xx is a meaningful answer,
 * and masking it would hide wrong credentials, a blocked approval, or a contract
 * error — so those always surface as errors.
 */
export function shouldFallback(status: number): boolean {
  return status === 0 || status >= 500;
}

// ---------- token ----------
// sessionStorage: survives a reload, forgotten when the tab closes.
let token: string | null = sessionStorage.getItem("token");
let currentUser: User | null = readStoredUser();

function readStoredUser(): User | null {
  try {
    const raw = sessionStorage.getItem("demo_user");
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function setToken(t: string | null) {
  token = t;
  if (t) sessionStorage.setItem("token", t);
  else sessionStorage.removeItem("token");
}

export function setCurrentUser(u: User | null) {
  currentUser = u;
  if (u) sessionStorage.setItem("demo_user", JSON.stringify(u));
  else sessionStorage.removeItem("demo_user");
}

export const logout = () => {
  setToken(null);
  setCurrentUser(null);
};

export const hasToken = () => token !== null;

// ---------- helpers ----------

const parseBody = (body: BodyInit | null | undefined): any => {
  if (typeof body !== "string" || !body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
};

/** Unwrap a server or fixture error body into a plain message. */
function detailOf(body: unknown, fallbackText: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors arrive as a list.
  if (Array.isArray(detail))
    return "Invalid input: " + (detail[0]?.msg ?? "check the form");
  return fallbackText;
}

const answerFromFixtures = (method: string, path: string, body: any) =>
  mockForNow(method, path, body, { user: currentUser });

/**
 * Answer from mock_for_now/. If the fixture cannot answer either (an unknown
 * incident id, say), the original error is thrown so the real reason still shows.
 */
function fallback<T>(
  method: string,
  path: string,
  body: any,
  reason: string,
  originalError: ApiError,
): T {
  const r = answerFromFixtures(method, path, body);
  if (r.status >= 400) {
    report({ path, method, source: "fallback", reason });
    throw originalError;
  }
  report({ path, method, source: "fallback", reason });
  return r.body as T;
}

// ---------- the one function every screen uses ----------
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const body = parseBody(options.body);

  if (USE_MOCKS) {
    const r = answerFromFixtures(method, path, body);
    report({ path, method, source: "mock", reason: "" });
    if (r.status >= 400)
      throw new ApiError(
        r.status,
        detailOf(r.body, `Request failed (${r.status})`),
      );
    return r.body as T;
  }

  // ---- live ----
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response | null = null;
  let failure = "";

  try {
    res = await fetch(API_BASE + path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch (err: any) {
    failure =
      err?.name === "AbortError"
        ? `no answer within ${REQUEST_TIMEOUT_MS / 1000}s`
        : "unreachable";
  } finally {
    clearTimeout(timer);
  }

  if (res) {
    // Gone or expired token. Never a fallback case: a wrong password or a dead
    // session has to stay visible.
    if (res.status === 401 && path !== "/auth/login") {
      logout();
      window.location.assign("/login");
      throw new ApiError(401, "Please log in again.");
    }

    // The server may serve fixtures of its own and mark them.
    let headerMock = false;
    try {
      headerMock =
        (res.headers.get(MOCK_HEADER) ?? "").trim().toLowerCase() === "true";
    } catch {
      headerMock = false;
    }

    if (res.ok) {
      report({
        path,
        method,
        source: headerMock ? "mock" : "live",
        reason: headerMock ? `${MOCK_HEADER}: true response header` : "",
      });
      if (res.status === 204) return undefined as T;
      return (await res.json()) as T;
    }

    const payload = await res.json().catch(() => null);
    const serverError = new ApiError(
      res.status,
      detailOf(payload, res.statusText || `Request failed (${res.status})`),
    );

    if (!shouldFallback(res.status) || !hasFixture(method, path))
      throw serverError;
    return fallback<T>(method, path, body, `HTTP ${res.status}`, serverError);
  }

  const offlineError = new ApiError(0, NETWORK_ERROR);
  if (!hasFixture(method, path)) throw offlineError;
  return fallback<T>(method, path, body, failure || "unreachable", offlineError);
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const data = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  setCurrentUser(data.user);
  return data;
}

export const api = {
  me: () => request<User>("/me"),

  findings: () => request<Finding[]>("/findings"),

  incident: (id: string) =>
    request<Incident>(`/incidents/${encodeURIComponent(id)}`),

  approve: (id: string) =>
    request<DecisionResponse>(
      `/incidents/${encodeURIComponent(id)}/approve`,
      {
        method: "POST",
      },
    ),

  reject: (id: string, reason: string) =>
    request<DecisionResponse>(
      `/incidents/${encodeURIComponent(id)}/reject`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),

  lessons: () => request<Lesson[]>("/lessons"),

  overview: () => request<GroupOverview>("/group/overview"),

  risks: () => request<RiskRow[]>("/group/risks"),

  pushRisk: (id: string, company_id: string) =>
    request<PushRiskResponse>(
      `/group/risks/${encodeURIComponent(id)}/push`,
      {
        method: "POST",
        body: JSON.stringify({ company_id }),
      },
    ),

  meko: () => request<MekoSetting>("/settings/meko"),

  setMeko: (mode: "on" | "off") =>
    request<MekoSetting>("/settings/meko", {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
};

export { FINAL_STATUSES };

/** True when polling should stop for this incident status. */
export const isFinalStatus = (status: unknown): boolean =>
  FINAL_STATUSES.includes(String(status).toLowerCase() as any);
