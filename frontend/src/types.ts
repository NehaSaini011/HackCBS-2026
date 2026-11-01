// Contract types for the Group API.
// These mirror the shapes agreed with Person 2 (Team Integration Guide, section 3b).
// The mock data in ./data.ts is written against these same shapes on purpose: when
// VITE_USE_MOCKS flips to false, nothing about the screens has to change.

export type Role = "group_admin" | "engineer";
export type Severity = "info" | "warning" | "critical";

export type Status =
  | "open"
  | "diagnosed"
  | "proving"
  | "awaiting_approval"
  | "applying"
  | "resolved"
  | "rejected"
  | "unknown"
  | "proof_failed";

// Statuses after which nothing changes any more. Polling stops here.
export const FINAL_STATUSES: Status[] = [
  "resolved",
  "rejected",
  "unknown",
  "proof_failed",
];

export interface CompanyRef {
  id: string;
  name: string;
}

export interface User {
  id: string;
  email: string;
  role: Role;
  group_id: string;
  company: CompanyRef | null;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface Finding {
  id: string;
  company: CompanyRef;
  test: string;
  source: string;
  severity: Severity;
  summary: string;
  status: Status;
  incident_id: string | null;
  duplicates: number;
  first_seen: string;
  last_seen: string;
  lesson_id?: string | null;
}

export interface Evidence {
  check: string;
  query: string;
  result: string;
  // Presentation hint only. The API does not send this; when it is absent the
  // evidence row is rendered neutrally rather than guessing pass or fail.
  status?: "pass" | "fail" | "warn";
}

export interface Diagnosis {
  cause_class: "MISSING_INDEX" | "LOCK_CONTENTION" | "UNKNOWN";
  explanation: string;
  evidence: Evidence[];
}

export interface RecalledLesson {
  id: string;
  cause_class: string;
  confirmations: number;
  status: string;
  fix_shape?: string | null;
}

export interface Fix {
  template: string;
  sql: string;
  test_sql?: string;
  params?: unknown[];
}

export interface Proof {
  method: "fork" | "fake" | "none";
  fix_sql?: string;
  before_p95_ms: number | null;
  after_p95_ms: number | null;
  passed: boolean;
  error?: string | null;
  fork_id?: string | null;
}

export interface Decision {
  approved: boolean;
  by: string;
  reason: string | null;
  at: string;
}

export interface DecisionResponse {
  status: Status;
  decision: Decision;
}

export interface PushRiskResponse {
  finding_id: string;
  lesson_id: string;
}

export interface MekoEvent {
  op: "recall" | "store" | "share" | "skipped" | "error";
  text: string;
  at: string;
}

export interface Timeline {
  first_alert_at: string | null;
  diagnosed_at: string | null;
  proven_at: string | null;
  decided_at: string | null;
  resolved_at: string | null;
}

export interface Incident {
  id: string;
  company: CompanyRef;
  finding_ids: string[];
  status: Status;
  diagnosis: Diagnosis | null;
  recalled_lesson: RecalledLesson | null;
  fix: Fix | null;
  proof: Proof | null;
  decision: Decision | null;
  applied?: boolean;
  meko_activity: MekoEvent[];
  timeline: Timeline;
  meko_mode: "on" | "off";
}

export interface Lesson {
  id: string;
  cause_class: string;
  symptoms: string[];
  fix_template: string;
  fix_shape?: string | null;
  fix_description: string;
  status: "seeded" | "proven" | "failed" | "needs_review";
  confirmations: number;
  failures: number;
  trust_score: number;
  source: "agent" | "postmortem";
  created_at?: string;
}

export interface CompanyCard {
  company: CompanyRef;
  tech_stack?: string | null;
  open_findings: Record<Severity, number>;
  open_risks: number;
  last_incident: { id: string; status: Status; at: string | null } | null;
}

export type GroupOverview = CompanyCard[];

export interface RiskCompany {
  id: string;
  name: string;
  status: "open" | "pushed" | "resolved";
  finding_id: string | null;
}

export interface RiskRow {
  id: string;
  risk_type: string;
  companies: RiskCompany[];
  proven_lesson: {
    id: string;
    cause_class: string;
    confirmations: number;
    trust_score: number;
  } | null;
  affected: number;
}

export interface MekoSetting {
  mode: "on" | "off";
}
