import { useEffect, useState, type ReactNode } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Check,
  Eye,
  EyeOff,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  API_BASE,
  MOCK_HEADER,
  USE_MOCKS,
  api,
  getTransport,
  hasToken,
  isFinalStatus,
  login,
  logout,
  subscribeTransport,
  type Source,
} from "./api";
import type {
  CompanyCard,
  Evidence as EvidenceRow,
  Finding,
  Incident as IncidentRecord,
  Lesson,
  RiskRow,
} from "./types";
import { usePoll } from "./usePoll";

// ---------- helpers ----------

/** "missing_index" -> "Missing index" */
const words = (s: unknown) =>
  String(s ?? "")
    .replaceAll("_", " ")
    .replace(/^\w/, (c) => c.toUpperCase());

const clock = (iso?: string | null) => {
  if (!iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleTimeString();
};
const formatDuration = (
  start?: string | null,
  end?: string | null,
) => {
  if (!start || !end) return DASH;

  const startTime = new Date(start).getTime();
  const endTime = new Date(end).getTime();

  if (
    Number.isNaN(startTime) ||
    Number.isNaN(endTime) ||
    endTime < startTime
  ) {
    return DASH;
  }

  const totalSeconds = Math.floor((endTime - startTime) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return minutes > 0
    ? `${minutes}m ${seconds}s`
    : `${seconds}s`;
};

const stamp = (ms: number | null) =>
  ms === null ? "not yet" : new Date(ms).toLocaleTimeString();

/** The missing-value mark. A real zero prints as a zero; only a missing value is a dash.
    taste-skill-ignore: the em dash here is the dash §11 of the app-screen rules requires. */
const DASH = "—";

/** A real count. Zero prints as zero; a missing value as a dash. */
const count = (n: number | null | undefined) =>
  typeof n === "number" ? n : DASH;

/** Status tone: proven is good, failed is bad, everything else is a warning. */
const statusTone = (status: string) =>
  status === "proven" ? "pos" : status === "failed" ? "neg" : "warn";

const CAUSE_TITLES: Record<string, string> = {
  MISSING_INDEX: "Missing index after a release",
  LOCK_CONTENTION: "Lock contention on a long transaction",
  UNKNOWN: "Cause not established yet",
};

function proofMethodLabel(proof: IncidentRecord["proof"]): string {
  if (!proof) return "No proof has been produced yet.";
  if (proof.method === "fake")
    return "Simulated proof (test mode). This is not a real test result.";
  if (proof.method === "fork")
    return `Tested on an isolated copy of the database${
      proof.fork_id ? ` (${proof.fork_id})` : ""
    }, then the copy was deleted.`;
  return "Not tested.";
}

// ---------- shared pieces ----------

/** The product's mark: the three-node network from the brand artwork. */
function Mark({ size = 26 }: { size?: number }) {
  return (
    <img
      src="/logo.png"
      alt=""
      aria-hidden="true"
      style={{ height: size, width: "auto", flex: "none" }}
    />
  );
}

/** Where this panel's body came from, in words, inside the block it describes. */
function Foot({
  note,
  intervalMs,
  lastUpdated,
  source,
}: {
  note: string;
  intervalMs: number;
  lastUpdated: number | null;
  source: Source;
}) {
  const origin =
    source === "fallback"
      ? "MOCK FALLBACK"
      : source === "mock"
        ? "MOCK DATA"
        : `Live · ${API_BASE}`;
  return (
    <p className="page-foot">
      <span>{note}</span>
      <span>
        {origin} ·{" "}
        {intervalMs > 0
          ? `re-read every ${intervalMs / 1000}s`
          : "read on open"}{" "}
        · updated {stamp(lastUpdated)}
      </span>
    </p>
  );
}

/** An error inside the block that failed, never a full-screen banner. */
function BlockError({
  error,
  onRetry,
}: {
  error: string;
  onRetry?: () => void;
}) {
  return (
    <div className="block-error">
      <span>
        <b>Couldn’t load this block.</b> {error}
      </span>
      {onRetry && (
        <button className="btn sm" onClick={onRetry}>
          <RefreshCw size={12} /> Retry
        </button>
      )}
    </div>
  );
}

function TitleRow({
  scope,
  title,
  sub,
  children,
}: {
  scope: ReactNode;
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <div className="title-row">
      <div>
        <p className="scope">{scope}</p>
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {children && <div className="title-actions">{children}</div>}
    </div>
  );
}

function Loading({ w = 220 }: { w?: number }) {
  return <div className="skeleton" style={{ width: w }} />;
}

// ---------- login ----------

function Login({ done }: any) {
  const [email, S] = useState(""),
    [pw, P] = useState(""),
    [show, SH] = useState(false),
    [err, E] = useState(""),
    [busy, B] = useState(false);
  const nav = useNavigate();

  const accounts: [string, string][] = [
    ["priya@tealbox.demo", "Priya, on call at Tealbox"],
    ["arjun@pinecart.demo", "Arjun, on call at Pinecart"],
    ["platform@fund1.demo", "Platform team, group admin"],
  ];

  async function submit(e: any) {
    e.preventDefault();
    B(true);
    E("");
    try {
      const d = await login(email, pw);
      done(d.user);
      nav(d.user.role === "group_admin" ? "/group" : "/findings");
    } catch (x: any) {
      E(x.message);
    } finally {
      B(false);
    }
  }

  return (
    <div className="login">
      <div className="login-inner">
        <div className="login-mark" style={{fontSize: "17px"}}>
          <Mark size={40} />
          <h1>Outage Herd Immunity</h1>
        </div>

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Work email</label>
            <input
              id="email"
              className="input"
              placeholder="Enter your work email"
              type="email"
              value={email}
              onChange={(e) => S(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <span className="input-wrap">
              <input
                id="password"
                placeholder="Enter your password"
                className="input"
                type={show ? "text" : "password"}
                value={pw}
                onChange={(e) => P(e.target.value)}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="reveal"
                aria-pressed={show}
                aria-label={show ? "Hide password" : "Show password"}
                title={show ? "Hide password" : "Show password"}
                onClick={() => SH(!show)}
              >
                {show ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </span>
          </div>
          {err && <BlockError error={err} />}
          <button className="btn primary full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"} <ArrowRight size={15} />
          </button>
        </form>

        <div className="demo-accounts">
          <p className="meta">Demo accounts</p>
          <div className="rows">
            {accounts.map(([mail, who]) => (
              <div className="row" key={mail}>
                <div className="grow">
                  <span className="mail">{mail}</span>
                  <span className="sub who">{who}</span>
                </div>
                <button
                  className="btn sm"
                  type="button"
                  onClick={() => {
                    S(mail);
                    P("demo123");
                  }}
                >
                  Use
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- app ----------

function App() {
  const [user, U] = useState<any>(null),
    [boot, B] = useState(hasToken()),
    [bootError, BE] = useState("");
  useEffect(() => {
    if (!hasToken()) {
      B(false);
      return;
    }
    let alive = true;
    api
      .me()
      .then((u) => alive && U(u))
      .catch((e: any) => {
        if (!alive) return;
        logout();
        BE(`Could not restore your session: ${e?.message ?? e}`);
      })
      .finally(() => alive && B(false));
    return () => {
      alive = false;
    };
  }, []);

  if (boot) return <div className="boot">Checking your session…</div>;

  return (
    <>
      {bootError && !user && (
        <div style={{ padding: 16 }}>
          <BlockError error={bootError} onRetry={() => location.reload()} />
        </div>
      )}
      <Routes>
        <Route
          path="/login"
          element={
            user ? (
              <Navigate
                to={user.role === "group_admin" ? "/group" : "/findings"}
              />
            ) : (
              <Login done={U} />
            )
          }
        />
        <Route
          path="/"
          element={
            <Navigate
              to={
                user
                  ? user.role === "group_admin"
                    ? "/group"
                    : "/findings"
                  : "/login"
              }
            />
          }
        />
        <Route
          path="/*"
          element={
            user ? (
              <Shell
                user={user}
                exit={() => {
                  logout();
                  U(null);
                }}
              />
            ) : (
              <Navigate to="/login" />
            )
          }
        />
      </Routes>
    </>
  );
}

function Shell({ user, exit }: any) {
  const { pathname } = useLocation();
  const [transport, setTransport] = useState(getTransport());
  useEffect(() => subscribeTransport(setTransport), []);

  const admin = user.role === "group_admin";
  const source: Source = USE_MOCKS ? "mock" : transport.source;
  const fallingBack = source === "fallback";

  const items: [string, string, any][] = admin
    ? [
        ["/group", "Overview", LayoutDashboard],
        ["/risks", "Risks", AlertTriangle],
        ["/lessons", "Lessons", BookOpen],
        ["/meko", "Meko", Sparkles],
      ]
    : [
        ["/findings", "Findings", Activity],
        ["/lessons", "Lessons", BookOpen],
      ];

  const modeLabel =
    source === "mock" ? "Mock" : fallingBack ? "Mock fallback" : "Live";
  const modeClass =
    source === "mock"
      ? "mode-dot mock"
      : fallingBack
        ? "mode-dot fallback"
        : "mode-dot";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="rail-mark" title="Outage Herd Immunity">
          <Mark />
        </div>
        <nav className="rail-items" aria-label="Screens">
          {items.map(([to, label, Icon]) => (
            <Link
              key={to}
              to={to}
              className="nav-item"
              title={label}
              aria-label={label}
              aria-current={pathname === to ? "page" : undefined}
            >
              <Icon />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="rail-foot">
          <span className="rail-sep" />
          <span
            className={modeClass}
            aria-label={`Data source: ${modeLabel}`}
            title={`Data source: ${modeLabel}`}
          >
            <i />
          </span>
          <button
            className="nav-item"
            onClick={exit}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="canvas">
        {fallingBack && (
          <div className="notice warn">
            <AlertTriangle size={14} style={{ flex: "none" }} />
            <span>
              <b>
                The API did not answer {transport.method}{" "}
                <code>{transport.path}</code>
              </b>{" "}
              ({transport.reason}). Everything on this screen comes from the
              scripted fixtures in <code>mock_for_now/</code>, so treat it as
              examples rather than results. It keeps retrying on its own, and a
              fixture is marked <code>{MOCK_HEADER}: true</code>.
            </span>
          </div>
        )}

        <Routes>
          <Route path="/findings" element={<Findings user={user} />} />
          <Route path="/incident/:id" element={<IncidentRoute />} />
          <Route path="/lessons" element={<Lessons />} />
          <Route path="/group" element={<Group />} />
          <Route path="/risks" element={<Risks />} />
          <Route path="/meko" element={<Meko />} />
          <Route
            path="*"
            element={<Navigate to={admin ? "/group" : "/findings"} />}
          />
        </Routes>
      </div>
    </div>
  );
}

// ---------- findings inbox ----------

const FINDINGS_INTERVAL_MS = 2000;

function Findings({ user }: any) {
  const poll = usePoll<Finding[]>(() => api.findings(), {
    intervalMs: FINDINGS_INTERVAL_MS,
  });
  const [filter, F] = useState("all"),
    [q, Q] = useState("");

  const data = poll.data ?? [];
  const rows = data
    .filter(
      (x) =>
        (filter === "all" || x.severity === filter || x.status === filter) &&
        String(x.summary ?? "")
          .toLowerCase()
          .includes(q.toLowerCase()),
    )
    .slice()
    .sort((a, b) => String(b.last_seen).localeCompare(String(a.last_seen)));

  const open = data.filter((x) => x.status !== "resolved").length;
  const critical = data.filter((x) => x.severity === "critical").length;
  const awaiting = data.filter((x) => x.status === "awaiting_approval").length;
  const resolved = data.filter((x) => x.status === "resolved").length;

  return (
    <>
      <TitleRow
        scope={`${user.company?.name ?? "Tealbox"} · on call`}
        title="Findings inbox"
        sub={
          awaiting > 0
            ? `${awaiting} finding${awaiting === 1 ? " is" : "s are"} waiting on your approval, and the proof is already in.`
            : "Nothing is waiting on you. New findings land here as they arrive."
        }
      >
        <button className="btn" onClick={poll.refresh} disabled={poll.busy}>
          <RefreshCw size={13} /> {poll.busy ? "Refreshing…" : "Refresh"}
        </button>
      </TitleRow>

      <div className="kpis">
        <div className="kpi">
          <p className="kpi-label">Awaiting your approval</p>
          <p className="kpi-value lead">{count(awaiting)}</p>
          <p className="kpi-note">Proof is ready to review</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Open findings</p>
          <p className="kpi-value">{count(open)}</p>
          <p className="kpi-note">This company</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Critical</p>
          <p className="kpi-value">{count(critical)}</p>
          <p className="kpi-note">Needs attention</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Resolved</p>
          <p className="kpi-value">{count(resolved)}</p>
          <p className="kpi-note">In this list</p>
        </div>
      </div>

      <div className="filters">
        <label className="search">
          <Search size={14} />
          <input
            placeholder="Search findings"
            aria-label="Search findings"
            value={q}
            onChange={(e) => Q(e.target.value)}
          />
        </label>
        <select
          className="input"
          aria-label="Filter by status"
          value={filter}
          onChange={(e) => F(e.target.value)}
        >
          <option value="all">All statuses</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="awaiting_approval">Awaiting approval</option>
          <option value="proof_failed">Proof failed</option>
          <option value="resolved">Resolved</option>
          <option value="unknown">Unknown</option>
        </select>
        <span className="spacer" />
        <span className="stamp">
          re-read every {FINDINGS_INTERVAL_MS / 1000}s ·{" "}
          {stamp(poll.lastUpdated)}
        </span>
      </div>

      {poll.error && <BlockError error={poll.error} onRetry={poll.refresh} />}

      <div className="panel" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table aria-label="Findings for this company, newest first">
            <thead>
              <tr>
                <th>Finding</th>
                <th>Severity</th>
                <th>Source</th>
                <th>Status</th>
                <th className="n">Occurrences</th>
                <th className="n">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr
                  key={f.id}
                  className={
                    f.status === "awaiting_approval" ? "needs-you" : undefined
                  }
                >
                  <td>
                    {f.incident_id ? (
                      <Link
                        className="row-link"
                        to={"/incident/" + f.incident_id}
                      >
                        <span className="name">{f.summary}</span>
                        <span className="sub">
                          {f.company?.name} · {words(f.test)}
                        </span>
                      </Link>
                    ) : (
                      <>
                        <span className="name">{f.summary}</span>
                        <span className="sub">
                          {f.company?.name} · {words(f.test)}
                        </span>
                        <span className="sub" style={{ color: "var(--pill-warning-ink)" }}>
                          Waiting for agent
                        </span>
                      </>
                    )}
                  </td>
                  <td>
                    <span
                      className={
                        "pill " +
                        (f.severity === "critical"
                          ? "neg"
                          : f.severity === "warning"
                            ? "warn"
                            : "")
                      }
                    >
                      {f.severity}
                    </span>
                  </td>
                  <td className="id">{f.source}</td>
                  <td>
                    <span
                      className={
                        "pill " +
                        (f.status === "resolved"
                          ? "pos"
                          : f.status === "proof_failed"
                            ? "neg"
                            : "")
                      }
                    >
                      {words(f.status).toLowerCase()}
                    </span>
                  </td>
                  <td className="n">{count(f.duplicates)}</td>
                  <td className="n">{clock(f.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {poll.loading && (
          <div style={{ padding: 20 }}>
            <Loading />
          </div>
        )}
        {!poll.loading && rows.length === 0 && (
          <div style={{ padding: 20 }}>
            <div className="empty">
              {data.length === 0
                ? "No finding has arrived for this company yet."
                : "No finding matches this filter."}
            </div>
          </div>
        )}

        <div style={{ padding: "0 20px" }}>
          <Foot
            note={`${rows.length} of ${data.length} findings shown`}
            intervalMs={FINDINGS_INTERVAL_MS}
            lastUpdated={poll.lastUpdated}
            source={poll.source}
          />
        </div>
      </div>

      <section className="panel" style={{ marginTop: "var(--gap)" }}>
        <header>
          <h2>Guardrails this screen enforces</h2>
        </header>
        <div className="rows">
          {[
            [
              "Evidence before action",
              "Read-only checks run before any diagnosis.",
            ],
            [
              "Proof on a copy",
              "The candidate fix is measured on an isolated copy first.",
            ],
            [
              "A human decides",
              "No fix is applied without an engineer clicking approve.",
            ],
            [
              "Data stays home",
              "A shared lesson carries the pattern, never your query text.",
            ],
          ].map(([t, d]) => (
            <div className="row" key={t}>
              <Check
                size={15}
                strokeWidth={1.5}
                style={{ color: "var(--muted)", flex: "none" }}
              />
              <div className="grow">
                <span>{t}</span>
                <span className="sub">{d}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

// ---------- incident detail ----------

function IncidentRoute() {
  const { id = "inc_12" } = useParams();
  return <Incident key={id} id={id} />;
}

function Incident({ id }: { id: string }) {
  const poll = usePoll<IncidentRecord>(() => api.incident(id), {
    intervalMs: 2000,
    shouldContinue: (inc) => !isFinalStatus(inc.status),
  });
  const [reason, R] = useState(""),
    [rejecting, J] = useState(false),
    [actionError, AE] = useState(""),
    [deciding, DEC] = useState(false);
  const [decided, setDecided] = useState<IncidentRecord | null>(null);
  useEffect(() => {
    setDecided(null);
  }, [poll.data]);

  const x = decided ?? poll.data;

  if (!x)
    return (
      <>
        <TitleRow scope="Incident" title="Loading the incident…" />
        {poll.error ? (
          <BlockError error={poll.error} onRetry={poll.refresh} />
        ) : (
          <div className="panel">
            <Loading w={280} />
          </div>
        )}
      </>
    );

  const proof = x.proof ?? null;
  const passed = proof?.passed === true;
  const simulated = passed && proof?.method === "fake";
  const diagnosis = x.diagnosis ?? null;
  const evidence: EvidenceRow[] = diagnosis?.evidence ?? [];
  const decision = x.decision ?? null;
  const activity = x.meko_activity ?? [];
  const timeToProvenFix = formatDuration(
    x.timeline?.first_alert_at,
    x.timeline?.proven_at,
  );
  const finished = isFinalStatus(x.status);
  const canDecide = passed && !decision;

  const before = proof?.before_p95_ms ?? null;
  const after = proof?.after_p95_ms ?? null;
  const widest = Math.max(before ?? 0, after ?? 0) || 1;
  const reduction =
    before != null && after != null && before > 0
      ? Math.round(((before - after) / before) * 1000) / 10
      : null;

  async function decide(a: "approve" | "reject") {
    DEC(true);
    AE("");

    try {
      if (a === "approve") {
        await api.approve(id);
      } else {
        await api.reject(id, reason);
      }

      const updatedIncident = await api.incident(id);

      setDecided(updatedIncident);
      J(false);
      poll.refresh();
    } catch (e: any) {
      AE(e?.message ?? String(e));
    } finally {
      DEC(false);
    }
  }

  const stages: [string, string | null | undefined][] = [
    ["Alert", x.timeline?.first_alert_at],
    ["Diagnosis", x.timeline?.diagnosed_at],
    ["Proof", x.timeline?.proven_at],
    ["Decision", x.timeline?.decided_at],
    ["Resolved", x.timeline?.resolved_at],
  ];

  return (
    <>
      <TitleRow
        scope={
          <>
            Incident <b>{x.id}</b> · {x.company?.name ?? DASH}
          </>
        }
        title={
          CAUSE_TITLES[diagnosis?.cause_class ?? ""] ??
          "Incident under investigation"
        }
        sub={
          simulated
            ? "The candidate fix was measured as simulated proof. These are example values, not a real test, and approval still needs your click."
            : passed
              ? "The candidate fix was proved on an isolated copy, and the copy was then deleted."
              : "Approval stays locked until the fix proves itself on an isolated copy."
        }
      >
        <span className="pill">{words(x.status).toLowerCase()}</span>
      </TitleRow>

      {poll.error && <BlockError error={poll.error} onRetry={poll.refresh} />}
      {actionError && <BlockError error={actionError} />}

      <section className="panel" style={{ marginBottom: "var(--gap)" }}>
        <header>
          <h2>How this incident got here</h2>
          <span className="meta">
            {finished ? "finished" : "re-read every 2s"}
          </span>
        </header>
        <div className="stages">
          {stages.map(([label, at], i) => (
            <div
              className={
                "stage " +
                (at ? "done" : "pending") +
                (label === "Proof" && proof && !passed ? " failed" : "")
              }
              key={i}
            >
              <p className="stage-label">
                <span className="stage-dot" aria-hidden="true" />
                {label}
              </p>
              <p className="stage-time">{at ? clock(at) : DASH}</p>
            </div>
          ))}
        </div>
        {import.meta.env.VITE_GRAFANA_URL && (
          <a
            className="card-link"
            style={{ marginTop: 12 }}
            href={import.meta.env.VITE_GRAFANA_URL}
            target="_blank"
            rel="noreferrer"
          >
            Latency in Grafana <ArrowRight size={13} />
          </a>
        )}
      </section>

      <section className="panel" style={{ marginBottom: "var(--gap)" }}>
        <header>
          <h2>Fix and proof</h2>
          {proof && (
            <span
              className={
                "pill " + (passed ? (simulated ? "warn" : "pos") : "neg")
              }
            >
              {simulated ? "simulated" : passed ? "proved" : "not proved"}
            </span>
          )}
        </header>
        <div className="grid top">
          <div className="col-7">
            {x.fix?.sql || proof?.fix_sql ? (
              <pre className="sql">{x.fix?.sql ?? proof?.fix_sql}</pre>
            ) : (
              <p className="note">No candidate fix has been proposed yet.</p>
            )}
            {x.fix?.template && (
              <p className="note">
                Fix shape: <span className="mono">{x.fix.template}</span>
              </p>
            )}
          </div>
          <div className="col-5">
            {before != null && after != null ? (
              <div className="proof-bars">
                <div className="proof-row before">
                  <span className="label">p95 before</span>
                  <span className="track">
                    <span
                      className="fill"
                      style={{ width: `${(before / widest) * 100}%` }}
                    />
                  </span>
                  <span className="value">{before} ms</span>
                </div>
                <div className="proof-row after">
                  <span className="label">p95 after</span>
                  <span className="track">
                    <span
                      className="fill"
                      style={{
                        width: `${Math.max((after / widest) * 100, 0.6)}%`,
                      }}
                    />
                  </span>
                  <span className="value">{after} ms</span>
                </div>
                {reduction != null && (
                  <p className="note">
                    −{reduction}% on the copy. {proofMethodLabel(proof)}
                  </p>
                )}
              </div>
            ) : (
              <p className="note">{proofMethodLabel(proof)}</p>
            )}
            {proof?.error && (
              <p className="note" style={{ color: "var(--negative)" }}>
                {proof.error}
              </p>
            )}
          </div>
        </div>
      </section>

      <div className="grid top">
        <div className="col-7" style={{ display: "grid", gap: "var(--gap)" }}>
          <section className="panel">
            <header>
              <h2>Diagnosis</h2>
              {diagnosis && (
                <span className="pill">{diagnosis.cause_class}</span>
              )}
            </header>
            {diagnosis ? (
              <>
                <p style={{ maxWidth: "62ch" }}>{diagnosis.explanation}</p>
                <div style={{ marginTop: 8 }}>
                  {evidence.length === 0 && (
                    <p className="note">No evidence recorded yet.</p>
                  )}
                  {evidence.map((e, i) => (
                    <Evidence key={i} e={e} />
                  ))}
                </div>
              </>
            ) : (
              <div className="empty">
                The agent is still collecting evidence. This panel fills in when
                a diagnosis exists.
              </div>
            )}
          </section>

          <section className="panel">
            <header>
              <h2>Privacy boundary</h2>
              <ShieldCheck
                size={15}
                strokeWidth={1.5}
                style={{ color: "var(--muted)" }}
              />
            </header>
            <p className="note">
              A shared lesson carries the cause class, the fix shape and the
              counts. It never carries table names, hostnames or raw query text.
            </p>
            <Foot
              note={
                finished
                  ? "Finished, so re-reading has stopped"
                  : "Watching this incident"
              }
              intervalMs={2000}
              lastUpdated={poll.lastUpdated}
              source={poll.source}
            />
          </section>
        </div>

        <div className="col-5" style={{ display: "grid", gap: "var(--gap)" }}>
          <section className="panel">
            <header>
              <h2>Your decision</h2>
              {decision && (
                <span className={"pill " + (decision.approved ? "pos" : "neg")}>
                  {decision.approved ? "approved" : "rejected"}
                </span>
              )}
            </header>
            {decision ? (
              <p className="note">
                {decision.approved ? "Approved" : "Rejected"} by{" "}
                <span className="mono">{decision.by}</span> at{" "}
                {clock(decision.at)}
                {decision.reason ? `: ${decision.reason}` : ""}
              </p>
            ) : (
              <p className="note">
                {passed
                  ? "Proof passed. Read the evidence before you approve."
                  : "Fix not tested: approval is locked."}
              </p>
            )}

            <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
              <button
                className="btn primary full"
                disabled={!canDecide || deciding}
                onClick={() => decide("approve")}
              >
                <Check size={15} />
                {deciding ? "Working…" : "Approve and apply the fix"}
              </button>
              <button
                className="btn full"
                disabled={!!decision || deciding}
                onClick={() => J(!rejecting)}
              >
                <X size={15} /> Reject
              </button>
              {rejecting && (
                <>
                  <div className="field">
                    <label htmlFor="reason">
                      Why are you rejecting this fix?
                    </label>
                    <textarea
                      id="reason"
                      className="input"
                      rows={2}
                      value={reason}
                      onChange={(e) => R(e.target.value)}
                    />
                  </div>
                  <button
                    className="btn full"
                    disabled={reason.trim().length < 3 || deciding}
                    onClick={() => decide("reject")}
                  >
                    Confirm rejection
                  </button>
                </>
              )}
            </div>
            <p className="note">
              No fix is applied without this click, and none can be approved
              before its proof passes.
            </p>
          </section>

          <section className="panel">
            <header>
              <h2>Shared lesson</h2>
            </header>
            {x.recalled_lesson ? (
              <>
                <p>
                  <span className="mono">{x.recalled_lesson.id}</span> ·{" "}
                  {words(x.recalled_lesson.cause_class)}
                </p>
                <p className="note">
                  Proven at {x.recalled_lesson.confirmations}{" "}
                  {x.recalled_lesson.confirmations === 1
                    ? "company"
                    : "companies"}{" "}
                  in the group, and re-proved on this one’s own data before you
                  see it.
                </p>
                <Link
                  className="card-link"
                  to="/lessons"
                  style={{ marginTop: 10 }}
                >
                  Open the lesson library <ArrowRight size={13} />
                </Link>
              </>
            ) : (
              <p className="note">
                {x.meko_mode === "off"
                  ? "Shared memory was off for this incident, so no lesson was looked up and the agent worked it out from scratch."
                  : "No shared lesson matched this pattern. The agent worked it out on its own."}
              </p>
            )}
          </section>

          <section className="panel">
            <header>
              <h2>Memory activity</h2>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <span className="pill">meko {x.meko_mode ?? DASH}</span>
                <span className="pill">
                  time to proven fix · {timeToProvenFix}
                </span>
              </div>
            </header>
            {activity.length ? (
              <div className="rows">
                {activity.map((a, i) => (
                  <div className="row" key={i}>
                    <span className="pill" style={{ flex: "none" }}>
                      {a.op}
                    </span>
                    <div className="grow">
                      <span>{a.text}</span>
                      <span className="sub">{clock(a.at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="note">
                No memory activity was recorded for this incident, and nothing
                is invented to fill this panel.
              </p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function Evidence({ e }: { e: EvidenceRow }) {
  const tone = e.status ?? "";
  return (
    <div className="evidence">
      <span className={"mark " + tone} aria-hidden="true" />
      <div>
        <p className="check">{words(e.check)}</p>
        <p className="result">{e.result}</p>
        {e.query && (
          <details className="query">
            <summary className="query-summary">The SQL the agent ran</summary>
            <pre>{e.query}</pre>
          </details>
        )}
      </div>
      <span className="value" style={{ color: "var(--muted)" }}>
        {e.status ?? ""}
      </span>
    </div>
  );
}

// ---------- lesson library ----------

function Lessons() {
  const poll = usePoll<Lesson[]>(() => api.lessons(), { intervalMs: 0 });
  const [filter, F] = useState("all");
  const data = poll.data ?? [];
  const rows = data.filter((l) => filter === "all" || l.status === filter);

  const by = (s: string) => data.filter((x) => x.status === s).length;
  const tabList: [string, string, number][] = [
    ["all", "All", data.length],
    ["proven", "Proven", by("proven")],
    ["seeded", "Untested", by("seeded")],
    ["needs_review", "Needs review", by("needs_review")],
    ["failed", "Failed", by("failed")],
  ];

  const proven = by("proven");

  return (
    <>
      <TitleRow
        scope="Shared knowledge · every company"
        title="Lesson library"
        sub={`${proven} of ${data.length || DASH} lessons has been proved on a company's own copy. The rest are postmortems or failures, and are labelled as such.`}
      />

      {poll.error && <BlockError error={poll.error} onRetry={poll.refresh} />}

      <div
        className="tabs"
        role="tablist"
        aria-label="Filter lessons by status"
      >
        {tabList.map(([id, label, n]) => (
          <button
            key={id}
            role="tab"
            aria-selected={filter === id}
            onClick={() => F(id)}
          >
            {label} <span className="mono">{n}</span>
          </button>
        ))}
      </div>

      <div className="grid top">
        <div className="panel col-7" role="tabpanel">
          {poll.loading && <Loading w={240} />}
          {!poll.loading && rows.length === 0 && (
            <div className="empty">No lesson has this status yet.</div>
          )}

          <div className="rows">
            {rows.map((l) => (
              <div className="row wrap" key={l.id}>
                <div className="grow">
                  <p>
                    <span className="mono" style={{ color: "var(--muted)" }}>
                      {l.id}
                    </span>{" "}
                    · {l.cause_class}
                    <span
                      className={"pill " + statusTone(l.status)}
                      style={{ marginLeft: 10 }}
                    >
                      {words(l.status).toLowerCase()}
                    </span>
                  </p>
                  <p style={{ marginTop: 4 }}>{l.fix_description}</p>
                  <p className="sub">
                    {l.fix_template}
                    {l.fix_shape ? ` · ${l.fix_shape}` : ""} · from {l.source}
                  </p>
                  {l.symptoms?.length ? (
                    <p className="sub">matches: {l.symptoms.join(" · ")}</p>
                  ) : null}
                  {l.status === "seeded" && (
                    <p
                      className="sub"
                      style={{ color: "var(--pill-warning-ink)" }}
                    >
                      Never tested by any company. Prove it before you reuse it.
                    </p>
                  )}
                  {l.status === "failed" && (
                    <p
                      className="sub"
                      style={{ color: "var(--pill-negative-ink)" }}
                    >
                      Failed validation. Not a proven fix.
                    </p>
                  )}
                  {l.status === "needs_review" && (
                    <p
                      className="sub"
                      style={{ color: "var(--pill-warning-ink)" }}
                    >
                      Waiting on a decision. Not yet trusted for reuse.
                    </p>
                  )}
                </div>
                <span className="stat">
                  <span>{l.confirmations} confirmed</span>
                  <span className="sub">trust {l.trust_score}</span>
                  <span className="sub">{l.failures} failed</span>
                </span>
              </div>
            ))}
          </div>

          <Foot
            note={`${rows.length} of ${data.length} lessons`}
            intervalMs={0}
            lastUpdated={poll.lastUpdated}
            source={poll.source}
          />
        </div>

        <div className="panel col-5">
          <header>
            <h2>What each status means</h2>
          </header>
          <div className="rows">
            {[
              [
                "proven",
                "A company proved this on its own copy and an engineer approved it.",
                "Reuse the pattern, then prove it again on yours.",
              ],
              [
                "seeded",
                "A published postmortem. Nobody in the group has run it on real data.",
                "Treat it as a lead. Do not apply it.",
              ],
              [
                "needs_review",
                "Proved once, and waiting on a decision from the group.",
                "Leave it alone until that decision lands.",
              ],
              [
                "failed",
                "A company tried it on its own copy and it did not pass.",
                "Do not reuse it, and do not re-propose it.",
              ],
            ].map(([status, meaning, next]) => (
              <div
                className="row"
                key={status}
                style={{ alignItems: "flex-start" }}
              >
                <span
                  className={"pill " + statusTone(status)}
                  style={{ flex: "none" }}
                >
                  {words(status).toLowerCase()}
                </span>
                <span className="grow">
                  <span>{meaning}</span>
                  <span className="sub">{next}</span>
                </span>
              </div>
            ))}
          </div>

          <header style={{ marginTop: 24 }}>
            <h2>How a lesson reaches this library</h2>
          </header>
          <div className="rows">
            {[
              "An incident is diagnosed, and shared memory is searched for a matching pattern.",
              "The candidate fix is proved on the affected company's own database copy.",
              "An engineer reads the evidence and approves it. Nothing is applied before that click.",
              "The pattern is redacted and shared. Table names, hostnames and query text stay behind.",
            ].map((step) => (
              <div className="row" key={step}>
                <span className="grow">{step}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

// ---------- group overview ----------

const GROUP_INTERVAL_MS = 5000;

function Group() {
  const poll = usePoll<{ overview: CompanyCard[]; risks: RiskRow[] }>(
    async () => {
      const [overview, risks] = await Promise.all([
        api.overview(),
        api.risks(),
      ]);
      return { overview, risks };
    },
    { intervalMs: GROUP_INTERVAL_MS },
  );

  const cards: CompanyCard[] = poll.data?.overview ?? [];
  const rs: RiskRow[] = poll.data?.risks ?? [];

  const openFindings = cards.reduce(
    (t, c) =>
      t +
      (c.open_findings?.critical ?? 0) +
      (c.open_findings?.warning ?? 0) +
      (c.open_findings?.info ?? 0),
    0,
  );
  const critical = cards.reduce(
    (t, c) => t + (c.open_findings?.critical ?? 0),
    0,
  );
  const inTrouble = cards.filter(
    (c) => (c.open_findings?.critical ?? 0) > 0,
  ).length;

  const worst = [...cards].sort(
    (a, b) =>
      (b.open_findings?.critical ?? 0) - (a.open_findings?.critical ?? 0),
  )[0];

  return (
    <>
      <TitleRow
        scope="Founders Group · portfolio"
        title="Group overview"
        sub={
          worst && (worst.open_findings?.critical ?? 0) > 0
            ? `${worst.company.name} carries the only critical findings in the group. Every other company is holding.`
            : "Every company in the group is holding."
        }
      >
        <span className="stamp">
          re-read every {GROUP_INTERVAL_MS / 1000}s · {stamp(poll.lastUpdated)}
        </span>
      </TitleRow>

      {poll.error && <BlockError error={poll.error} onRetry={poll.refresh} />}

      <div className="kpis">
        <div className="kpi">
          <p className="kpi-label">Companies in trouble</p>
          <p className="kpi-value lead">{count(inTrouble)}</p>
          <p className="kpi-note">Carrying a critical finding</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Companies</p>
          <p className="kpi-value">{count(cards.length)}</p>
          <p className="kpi-note">In the group</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Open findings</p>
          <p className="kpi-value">{count(openFindings)}</p>
          <p className="kpi-note">Across the portfolio</p>
        </div>
        <div className="kpi">
          <p className="kpi-label">Critical findings</p>
          <p className="kpi-value">{count(critical)}</p>
          <p className="kpi-note">Require review</p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: "var(--gap)", padding: 0 }}>
        <div className="table-wrap">
          <table aria-label="Companies in the group">
            <thead>
              <tr>
                <th>Company</th>
                <th>Stack</th>
                <th className="n">Critical</th>
                <th className="n">Warning</th>
                <th className="n">Info</th>
                <th className="n">Open risks</th>
                <th>Last incident</th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => {
                const f = c.open_findings ?? {
                  critical: 0,
                  warning: 0,
                  info: 0,
                };
                return (
                  <tr key={c.company.id}>
                    <td>
                      <span className="name">{c.company.name}</span>
                    </td>
                    <td className="id">{c.tech_stack ?? DASH}</td>
                    <td
                      className="n"
                      style={{
                        color: f.critical
                          ? "var(--pill-negative-ink)"
                          : undefined,
                      }}
                    >
                      {f.critical}
                    </td>
                    <td className="n">{f.warning}</td>
                    <td className="n">{f.info}</td>
                    <td className="n">{c.open_risks}</td>
                    <td>
                      {c.last_incident ? (
                        <>
                          {words(c.last_incident.status).toLowerCase()}
                          <span className="sub">
                            {c.last_incident.id} · {clock(c.last_incident.at)}
                          </span>
                        </>
                      ) : (
                        <span style={{ color: "var(--muted)" }}>
                          No incidents yet
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {poll.loading && (
          <div style={{ padding: 20 }}>
            <Loading />
          </div>
        )}
        {!poll.loading && cards.length === 0 && (
          <div style={{ padding: 20 }}>
            <div className="empty">The API returned no companies.</div>
          </div>
        )}

        <div style={{ padding: "0 20px" }}>
          <Foot
            note={`${cards.length} companies`}
            intervalMs={GROUP_INTERVAL_MS}
            lastUpdated={poll.lastUpdated}
            source={poll.source}
          />
        </div>
      </div>

      <section className="panel">
        <header>
          <h2>Patterns the group shares</h2>
          <Link className="card-link" to="/risks">
            Open the risk board <ArrowRight size={13} />
          </Link>
        </header>
        <div className="rows">
          {rs.map((r) => (
            <div className="row" key={r.id}>
              <div className="grow">
                <span>{words(r.risk_type)}</span>
                <span className="sub">
                  {r.affected} of {cards.length || "—"} companies affected
                </span>
              </div>
              <span className={r.proven_lesson ? "pill pos" : "pill warn"}>
                {r.proven_lesson ? "proven fix available" : "no proven fix"}
              </span>
            </div>
          ))}
          {!poll.loading && rs.length === 0 && (
            <div className="empty">No shared risk patterns reported.</div>
          )}
        </div>
      </section>
    </>
  );
}

// ---------- risk board ----------

function Risks() {
  const poll = usePoll<RiskRow[]>(() => api.risks(), {
    intervalMs: GROUP_INTERVAL_MS,
  });
  const [msg, M] = useState("");
  const [err, E] = useState("");
  const [pushing, P] = useState<string | null>(null);
  const rs = poll.data ?? [];

  const pushable = rs.filter((r) => r.proven_lesson).length;

  // Built from the rows already on this screen: who is still open on what, and
  // whether a proven fix exists for it yet.
  const exposure = new Map<
    string,
    { name: string; open: string[]; covered: string[]; fixable: boolean }
  >();
  for (const r of rs) {
    for (const c of r.companies ?? []) {
      const row = exposure.get(c.id) ?? {
        name: c.name,
        open: [],
        covered: [],
        fixable: false,
      };
      if (c.status === "open") {
        row.open.push(words(r.risk_type));
        if (r.proven_lesson) row.fixable = true;
      } else {
        row.covered.push(words(r.risk_type));
      }
      exposure.set(c.id, row);
    }
  }
  const exposureRows = [...exposure.values()].sort(
    (a, b) => b.open.length - a.open.length,
  );

  async function push(r: RiskRow) {
    const target = r.companies?.[0];
    if (!target) {
      E("This risk has no company to push to.");
      return;
    }
    P(r.id);
    M("");
    E("");
    try {
      await api.pushRisk(r.id, target.id);
      M(`Sent to ${target.name}. It now has to prove the fix on its own copy.`);
      poll.refresh();
    } catch (e: any) {
      E(e?.message ?? String(e));
    } finally {
      P(null);
    }
  }

  return (
    <>
      <TitleRow
        scope="Founders Group · exposure"
        title="Risk board"
        sub={`A shared lesson is not a shared production fix. ${pushable} of ${rs.length || DASH} patterns already has a proven fix; the rest still need investigating.`}
      >
        <span className="stamp">
          re-read every {GROUP_INTERVAL_MS / 1000}s · {stamp(poll.lastUpdated)}
        </span>
      </TitleRow>

      {poll.error && <BlockError error={poll.error} onRetry={poll.refresh} />}
      {err && <BlockError error={err} />}

      <div className="panel">
        <header>
          <h2>Recurring patterns</h2>
          <span className="meta">{rs.length} patterns</span>
        </header>

        <div className="rows">
          {rs.map((r) => (
            <div
              className="row"
              key={r.id}
              style={{ alignItems: "flex-start" }}
            >
              <div className="grow">
                <p>{words(r.risk_type)}</p>
                <p className="sub">
                  {r.affected} {r.affected === 1 ? "company" : "companies"}{" "}
                  affected
                  {(r.companies ?? []).length
                    ? ` · ${(r.companies ?? [])
                        .map((c) => `${c.name} (${c.status})`)
                        .join(", ")}`
                    : ""}
                </p>
                <p className="sub">
                  {r.proven_lesson
                    ? `Proven lesson ${r.proven_lesson.id} · ${r.proven_lesson.confirmations} confirmations · trust ${r.proven_lesson.trust_score}`
                    : "No proven fix yet. Investigate before pushing anything."}
                </p>
              </div>
              {r.proven_lesson ? (
                <button
                  className="btn"
                  disabled={pushing === r.id}
                  onClick={() => push(r)}
                >
                  {pushing === r.id ? "Sending…" : "Push the fix"}
                </button>
              ) : (
                <span className="pill warn">nothing to push</span>
              )}
            </div>
          ))}
          {poll.loading && <Loading w={240} />}
          {!poll.loading && rs.length === 0 && (
            <div className="empty">The API returned no risks.</div>
          )}
        </div>

        {msg && (
          <p className="notice" style={{ marginTop: 16, marginBottom: 0 }}>
            {msg}
          </p>
        )}
        <Foot
          note={`${rs.length} patterns, ${pushable} with a proven fix`}
          intervalMs={GROUP_INTERVAL_MS}
          lastUpdated={poll.lastUpdated}
          source={poll.source}
        />
      </div>

      <section className="panel" style={{ marginTop: "var(--gap)" }}>
        <header>
          <h2>Who is still exposed</h2>
          <span className="meta">
            {exposureRows.filter((e) => e.open.length).length} companies with a
            pattern still open
          </span>
        </header>
        <div className="table-wrap">
          <table aria-label="Companies, the patterns still open on them, and what is covered">
            <thead>
              <tr>
                <th>Company</th>
                <th>Still open on</th>
                <th>Already covered</th>
                <th className="n">Proven fix exists</th>
              </tr>
            </thead>
            <tbody>
              {exposureRows.map((e) => (
                <tr key={e.name}>
                  <td>
                    <span className="name">{e.name}</span>
                  </td>
                  <td>
                    {e.open.length ? (
                      e.open.join(", ")
                    ) : (
                      <span style={{ color: "var(--muted)" }}>
                        Nothing open
                      </span>
                    )}
                  </td>
                  <td style={{ color: "var(--muted)" }}>
                    {e.covered.length ? e.covered.join(", ") : DASH}
                  </td>
                  <td className="n">
                    {e.open.length === 0 ? (
                      <span style={{ color: "var(--muted)" }}>{DASH}</span>
                    ) : e.fixable ? (
                      <span className="pill pos">yes</span>
                    ) : (
                      <span className="pill warn">not yet</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!poll.loading && exposureRows.length === 0 && (
          <div className="empty">No company appears in the risk rows yet.</div>
        )}
      </section>
    </>
  );
}

// ---------- meko settings ----------

function Meko() {
  const poll = usePoll<{
    setting: { mode: "on" | "off" };
    lessons: Lesson[];
  }>(
    async () => {
      const [setting, lessons] = await Promise.all([api.meko(), api.lessons()]);
      return { setting, lessons };
    },
    { intervalMs: 0 },
  );
  const [m, M] = useState<"on" | "off">("on"),
    [msg, S] = useState(""),
    [err, E] = useState(""),
    [busy, B] = useState(false);

  useEffect(() => {
    if (poll.data?.setting?.mode) M(poll.data.setting.mode);
  }, [poll.data]);

  const lessons = poll.data?.lessons ?? [];
  const proven = lessons.filter((l) => l.status === "proven");
  const untested = lessons.filter((l) => l.status === "seeded").length;

  async function toggle() {
    const next = m === "on" ? "off" : "on";
    B(true);
    S("");
    E("");
    try {
      const d = await api.setMeko(next);
      M(d.mode);
      S(
        `Shared memory is ${d.mode === "on" ? "on" : "off"}. The switch changes what the agent looks up; it never invents memory activity.`,
      );
    } catch (e: any) {
      E(e?.message ?? String(e));
    } finally {
      B(false);
    }
  }

  return (
    <>
      <TitleRow
        scope="Founders Group · demo controls"
        title="Meko settings"
        sub="Shared memory is what lets the second company skip the slow part of an investigation. It never lets a fix skip its proof."
      />

      {(err || poll.error) && (
        <BlockError
          error={err || poll.error}
          onRetry={err ? undefined : poll.refresh}
        />
      )}

      <section className="panel" style={{ marginBottom: "var(--gap)" }}>
        <div className="row" style={{ padding: 0, minHeight: 0 }}>
          <div className="grow">
            <p>
              Shared memory{" "}
              <span className={"pill " + (m === "on" ? "pos" : "")}>
                {m === "on" ? "on" : "off"}
              </span>
            </p>
            <p className="sub">
              {m === "on"
                ? "The agent looks a matching lesson up before it runs the full investigation, then proves the candidate on your own copy."
                : "The agent skips shared recall and investigates from scratch. Proof is still required before anything is applied."}
            </p>
          </div>
          <button
            className="switch"
            role="switch"
            aria-checked={m === "on"}
            aria-label="Shared memory"
            disabled={busy}
            onClick={toggle}
          />
        </div>
        {msg && <p className="note">{msg}</p>}
      </section>

      <div className="grid top">
        <section className="panel col-6">
          <header>
            <h2>What this switch changes</h2>
          </header>
          <div className="rows">
            <div className="row">
              <div className="grow">
                <span>Investigation path</span>
                <span className="sub">
                  {m === "on"
                    ? "Recall the lesson first, then prove it on your copy"
                    : "The full investigation runs from scratch"}
                </span>
              </div>
              <span className="pill">
                {m === "on" ? "recall first" : "from scratch"}
              </span>
            </div>
            <div className="row">
              <div className="grow">
                <span>Proof before approval</span>
                <span className="sub">Unchanged by this switch</span>
              </div>
              <span className="pill pos">always</span>
            </div>
            <div className="row">
              <div className="grow">
                <span>A human approves</span>
                <span className="sub">An engineer still clicks approve</span>
              </div>
              <span className="pill pos">always</span>
            </div>
            <div className="row">
              <div className="grow">
                <span>Company isolation</span>
                <span className="sub">
                  A lesson carries the pattern, never the data
                </span>
              </div>
              <span className="pill pos">on</span>
            </div>
          </div>
          <p className="note">
            Do not claim a time saving until five real runs per mode have been
            recorded. The figures on the inbox are labelled example values for
            exactly that reason.
          </p>
        </section>

        <section className="panel col-6">
          <header>
            <h2>Privacy and safety rules</h2>
          </header>
          <div className="rows">
            {[
              "Redact table names, column names, hostnames and query text before anything is shared.",
              "Prove the candidate on an isolated copy before a lesson is promoted.",
              "An agent can reach only its own company’s database.",
              "A human approves every fix; the platform never applies one on its own.",
              "A lesson never carries a customer name, an order id or a row from the source company.",
            ].map((r) => (
              <div className="row" key={r}>
                <ShieldCheck
                  size={15}
                  strokeWidth={1.5}
                  style={{ color: "var(--muted)", flex: "none" }}
                />
                <span className="grow">{r}</span>
              </div>
            ))}
          </div>
          <Foot
            note="Read on open"
            intervalMs={0}
            lastUpdated={poll.lastUpdated}
            source={poll.source}
          />
        </section>
      </div>

      <section className="panel" style={{ marginTop: "var(--gap)" }}>
        <header>
          <h2>What memory holds right now</h2>
          <span className="meta">
            {lessons.length} lessons · {proven.length} proved · {untested} never
            tested
          </span>
        </header>
        {lessons.length === 0 ? (
          <div className="empty">The lesson library is empty.</div>
        ) : (
          <div className="table-wrap">
            <table aria-label="What shared memory holds, and how far each lesson can be trusted">
              <thead>
                <tr>
                  <th>Lesson</th>
                  <th>Pattern</th>
                  <th className="n">Confirmed by</th>
                  <th className="n">Failed</th>
                  <th>What recall would give you</th>
                </tr>
              </thead>
              <tbody>
                {lessons.map((l) => (
                  <tr key={l.id}>
                    <td className="id">{l.id}</td>
                    <td>{words(l.cause_class)}</td>
                    <td className="n">{l.confirmations}</td>
                    <td className="n">{l.failures}</td>
                    <td>
                      {l.status === "proven" ? (
                        "A candidate fix to re-prove on your own copy"
                      ) : l.status === "seeded" ? (
                        <span style={{ color: "var(--muted)" }}>
                          A lead only. Nobody has tested it.
                        </span>
                      ) : l.status === "failed" ? (
                        <span style={{ color: "var(--pill-negative-ink)" }}>
                          Nothing. This one failed.
                        </span>
                      ) : (
                        <span style={{ color: "var(--muted)" }}>
                          A candidate awaiting a decision.
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">
          With memory on, the agent still has to prove the candidate on the
          affected company’s own copy. Recall shortens the search, never the
          proof.
        </p>
      </section>
    </>
  );
}

export default App;
