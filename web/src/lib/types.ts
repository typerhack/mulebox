// The shapes the dashboard's API sends (docs/interfaces-m2.md). Every field a server may
// leave out is optional: an older server, or a worker that has not reported, is not an error.

export type JobKind = "job" | "runner" | "upgrade";

export interface Question {
  number?: number;
  since?: number;
  reason: string;
  left_s: number;
}

export interface Doing {
  stage?: string | null;
  step?: string | null;
  cpu_pct?: number | null;
}

export interface CiResult {
  outcome?: string;
  step?: string;
  message?: string;
}

export interface Job {
  job_id: string;
  project?: string | null;
  job?: string | null;
  branch?: string | null;
  client?: string | null;
  client_os?: string | null;
  state: string;
  outcome?: string | null;
  shown_state?: string | null;
  exit_code?: number | null;
  worker?: string | null;
  pinned_worker?: string | null;
  kind: JobKind;
  section?: "running" | "queued" | "recent";
  position?: number | null;
  elapsed_s?: number | null;
  duration_s?: number | null;
  usual_s?: number | null;
  created_at?: number | null;
  started_at?: number | null;
  finished_at?: number | null;
  paused?: boolean;
  boost?: boolean;
  cancel_requested?: boolean;
  run_url?: string | null;
  ci_result?: CiResult | null;
  question?: Question | null;
  doing?: Doing | null;
  needs?: string[];
  can_run_on?: string[];
  waiting_for?: string | null;
}

export interface Step {
  stage: string;
  started_at: number;
  finished_at: number | null;
  bytes_downloaded?: number | null;
  failing_line?: string | null;
}

export interface Usual {
  runs?: number;
  job_s?: number | null;
  stages?: Record<string, number>;
}

export interface Activity {
  output_idle_s?: number | null;
  job_cpu_pct?: number | null;
}

export interface JobDetail extends Job {
  base_commit?: string | null;
  timeout_min?: number | null;
  toolchain?: unknown;
  setup?: string | null;
  command?: string | null;
  stop_text?: string | null;
  steps?: Step[];
  usual?: Usual | null;
  failed_stage?: string | null;
  activity?: Activity | null;
  log_size?: number;
}

export interface QueueSnapshot {
  now: number;
  running: Job[];
  queued: Job[];
  recent: Job[];
}

export type MachineState = "available" | "busy" | "offline" | "draining";

export interface Machine {
  name: string;
  state: MachineState | string;
  slots: number;
  free_slots: number;
  capabilities: string[];
  last_seen?: number | null;
  cpu_pct?: number | null;
  mem_pct?: number | null;
  cores?: number | null;
  net_in_kib_s?: number | null;
  net_out_kib_s?: number | null;
  jobs: Job[];
  host?: boolean;
  version?: string | null;
}

export interface Notice {
  kind: string;
  level: "danger" | "warning" | string;
  name?: string;
  text: string;
  fix: string;
}

export interface MachinesPanel {
  machines: Machine[];
  total: number;
  online: number;
  free_slots: number;
  notices?: Notice[];
}

export interface Disk {
  roots: string[];
  total: number;
  used: number;
  free: number;
}

export interface Sample {
  t: number;
  cpu?: number[] | null;
  memory?: { total: number; available: number; used: number } | null;
  self?: { cpu: number; rss: number } | null;
  disk?: Disk[] | null;
  docker?: number | null;
  viewers?: number | null;
}

export interface MachineMetrics {
  machine?: string;
  host?: boolean;
  last_seen?: number | null;
  history: Sample[];
}

export interface StatRow {
  key: string;
  seconds: number;
  runs: number;
  running: number;
  running_seconds: number;
  unknown: number;
}

export interface StatDay {
  from: number;
  runs: number;
  kinds?: Record<string, number>;
}

export interface Stats {
  from?: number;
  first_started_at?: number | null;
  total: StatRow;
  by: Record<string, StatRow[]>;
  days?: StatDay[];
  choices?: Record<string, string[]>;
}
