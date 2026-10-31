// Offline fixtures and the fallback engine.
//
// `mock_for_now/_manifest.json` maps a method + path to a JSON file in that folder.
// This module is used from two places:
//
//   1. Mock mode  — every request is answered here. Nothing touches the network.
//   2. Live mode  — when a call fails in a way that means "the backend cannot
//                   answer" (see shouldFallback in api.ts), the same fixture for
//                   that exact endpoint answers instead.
//
// Every answer is reported as mock, so a screen can always say whether the body it
// is showing came from the real pipeline or from `mock_for_now`.

import manifest from "../mock_for_now/_manifest.json";
import type {
  Decision,
  Finding,
  Incident,
  MekoSetting,
  RiskRow,
  User,
} from "./types";

interface Route {
  method: string;
  path: string;
  file: string;
  pick?: string;
}

const ROUTES: Route[] = (manifest as { routes: Route[] }).routes;

// Eager glob so the fixtures are bundled: no runtime fetch, no 404, and the folder
// is the single source of truth for both mock mode and the fallback.
const FILES = import.meta.glob("../mock_for_now/*.json", {
  eager: true,
  import: "default",
}) as Record<string, any>;

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

function file(name: string): any {
  const mod = FILES[`../mock_for_now/${name}`];
  if (mod === undefined)
    throw new Error(
      `mock_for_now/${name} is missing. Add the file and list it in mock_for_now/_manifest.json.`,
    );
  return mod;
}

// ---------- mutable working copies ----------
// The seeds are read-only; approve/reject/push/meko mutate these copies so the demo
// can move through the whole flow.
let incidents: Record<string, Incident> | null = null;
let findings: Finding[] | null = null;
let risks: RiskRow[] | null = null;
let meko: MekoSetting | null = null;

function ensureState() {
  incidents ??= clone(file("incidents.json"));
  findings ??= clone(file("findings.json"));
  risks ??= clone(file("group_risks.json"));
  meko ??= clone(file("meko.json"));
}

/** Reset the mutated state back to the fixtures. Used by tests. */
export function resetMockState() {
  incidents = null;
  findings = null;
  risks = null;
  meko = null;
  ensureState();
}

// ---------- route matching ----------

interface Matched {
  route: Route;
  params: Record<string, string>;
}

function match(method: string, path: string): Matched | null {
  for (const route of ROUTES) {
    if (route.method !== method) continue;
    const names: string[] = [];
    const pattern = new RegExp(
      "^" +
        route.path.replace(/\{(\w+)\}/g, (_: string, name: string) => {
          names.push(name);
          return "([^/]+)";
        }) +
        "$",
    );
    const m = pattern.exec(path);
    if (!m) continue;
    const params: Record<string, string> = {};
    names.forEach((n, i) => (params[n] = decodeURIComponent(m[i + 1])));
    return { route, params };
  }
  return null;
}

/** True when `mock_for_now` can answer this request. Gates the live-mode fallback. */
export function hasFixture(method: string, path: string): boolean {
  return match(method.toUpperCase(), path) !== null;
}

// ---------- the engine ----------

export interface MockResult {
  status: number;
  body: unknown;
}

export interface MockContext {
  /** The signed-in user, so a recorded decision names the right engineer. */
  user: User | null;
}

/** The mutable collection behind a fixture file, or the static file itself. */
function resource(name: string): any {
  ensureState();
  switch (name) {
    case "incidents.json":
      return incidents;
    case "findings.json":
      return findings;
    case "group_risks.json":
      return risks;
    case "meko.json":
      return meko;
    default:
      return file(name);
  }
}

/** Keep the inbox consistent with its incident. */
function syncFinding(incidentId: string, status: Finding["status"]) {
  ensureState();
  for (const f of findings!) {
    if (f.incident_id === incidentId) f.status = status;
  }
}

const ok = (body: unknown): MockResult => ({ status: 200, body: clone(body) });
const fail = (status: number, detail: string): MockResult => ({
  status,
  body: { detail },
});

export function mockForNow(
  method: string,
  path: string,
  body: any,
  ctx: MockContext,
): MockResult {
  const hit = match(method.toUpperCase(), path);
  if (!hit) return fail(404, `No fixture for ${method} ${path}`);
  const { route, params } = hit;

  // ---------- auth ----------
  if (route.path === "/auth/login") {
    const accounts = file("login.json") as Record<string, { token: string; user: User }>;
    const email = String(body?.email ?? "").trim().toLowerCase();
    const account = accounts[email];
    // The guide's mock accepts any password; the real server checks it.
    if (!account || !body?.password)
      return fail(401, "Wrong email or password.");
    return ok(account);
  }

  if (route.path === "/me") {
    const user = ctx.user ?? (file("me.json") as User);
    return ok(user);
  }

  // ---------- incidents ----------
  if (route.file === "incidents.json") {
    ensureState();
    const id = params.id;
    const incident = incidents![id];
    if (!incident) return fail(404, `No incident ${id}`);

    if (route.path.endsWith("/approve")) {
      if (method.toUpperCase() !== "POST") return fail(405, "Approve must use POST.");
      if (incident.proof?.passed !== true)
        return fail(409, "Fix not tested, or the test failed.");
      if (incident.decision) return fail(409, "A decision is already recorded.");
      incident.decision = {
        approved: true,
        by: ctx.user?.email ?? "unknown",
        reason: null,
        at: new Date().toISOString(),
      } satisfies Decision;
      incident.status = "applying";
      incident.timeline.decided_at = incident.decision.at;
      incident.meko_activity.push({
        op: "share",
        text: "Engineer approved the proof-backed fix; lesson promoted to shared memory",
        at: incident.decision.at,
      });
      syncFinding(id, "applying");
      return ok(incident);
    }

    if (route.path.endsWith("/reject")) {
      if (method.toUpperCase() !== "POST") return fail(405, "Reject must use POST.");
      if (incident.decision) return fail(409, "A decision is already recorded.");
      const reason = String(body?.reason ?? "").trim();
      if (reason.length < 3)
        return fail(422, "A rejection reason of at least 3 characters is required.");
      incident.decision = {
        approved: false,
        by: ctx.user?.email ?? "unknown",
        reason,
        at: new Date().toISOString(),
      } satisfies Decision;
      incident.status = "rejected";
      incident.timeline.decided_at = incident.decision.at;
      incident.meko_activity.push({
        op: "skipped",
        text: `Fix rejected by the engineer: ${reason}`,
        at: incident.decision.at,
      });
      syncFinding(id, "rejected");
      return ok(incident);
    }

    // A plain GET. An approved fix settles on the following read, so the change is
    // only visible because the detail page is polling.
    if (incident.status === "applying") {
      incident.status = "resolved";
      incident.applied = true;
      incident.timeline.resolved_at = new Date().toISOString();
      syncFinding(id, "resolved");
    }
    return ok(incident);
  }

  // ---------- risk push ----------
  if (route.path.endsWith("/push")) {
    if (method.toUpperCase() !== "POST") return fail(405, "Push must use POST.");
    ensureState();
    const risk = risks!.find((r) => r.id === params.id);
    if (!risk) return fail(404, `No risk ${params.id}`);
    if (!body?.company_id) return fail(422, "Push needs a company_id.");
    if (!risk.proven_lesson)
      return fail(409, "This risk has no proven lesson to push yet.");
    const target = risk.companies.find((c) => c.id === body.company_id);
    if (!target) return fail(404, `Risk ${params.id} does not affect ${body.company_id}`);
    target.status = "pushed";
    return ok({ ok: true, risk_id: params.id, company_id: body.company_id });
  }

  // ---------- Meko switch ----------
  if (route.path === "/settings/meko") {
    ensureState();
    if (method.toUpperCase() === "PUT") {
      if (body?.mode !== "on" && body?.mode !== "off")
        return fail(422, "mode must be 'on' or 'off'.");
      meko!.mode = body.mode;
    }
    return ok(meko);
  }

  // ---------- everything else is a static read ----------
  const resource_ = resource(route.file);
  if (route.pick) {
    const picked = resource_[params[route.pick]];
    if (picked === undefined) return fail(404, `No fixture for ${method} ${path}`);
    return ok(picked);
  }
  return ok(resource_);
}
