// Mirrors backend/app/schemas.py

export type Severity = "CRITICAL" | "MAJOR" | "MINOR" | "WARNING";
export type ServiceStatus = "UP" | "DEGRADED" | "DOWN";
export type ProtectionType = "NONE" | "1+1";
export type Rate = 100 | 200 | 400;

export interface NodeInfo {
  id: string;
  name: string;
  lat: number;
  lon: number;
  degree: number;
}

export interface LinkInfo {
  id: string;
  a: string;
  b: string;
  length_km: number;
  latency_ms: number;
  status: "UP" | "DOWN";
  utilization: number;
  used_channels: number;
  channels: (string | null)[];
  osnr_db: number | null;
  rx_power_dbm: number | null;
}

export interface PathInfo {
  nodes: string[];
  links: string[];
  length_km: number;
  latency_ms: number;
  hops: number;
}

export interface Leg {
  path: PathInfo;
  channel: number;
  frequency_thz: number;
}

export interface Service {
  id: string;
  name: string;
  src: string;
  dst: string;
  rate_gbps: Rate;
  modulation: string;
  protection: ProtectionType;
  status: ServiceStatus;
  active: "working" | "protection";
  working: Leg | null;
  protection_leg: Leg | null;
  switchovers: number;
  restorations: number;
  created_at: number;
}

export interface Alarm {
  id: number;
  type: string;
  severity: Severity;
  resource: string;
  message: string;
  raised_at: number;
  cleared_at: number | null;
  acknowledged: boolean;
}

export interface NetEvent {
  id: number;
  ts: number;
  level: "info" | "success" | "warning" | "critical";
  kind: string;
  message: string;
  service_id: string | null;
  link_id: string | null;
}

export interface Stats {
  services_total: number;
  services_by_status: Record<ServiceStatus, number>;
  alarms_by_severity: Record<Severity, number>;
  network_utilization: number;
  requests_total: number;
  blocked_total: number;
  blocking_probability: number;
  capacity_tbps: number;
  links_down: number;
}

export interface RateProfile {
  rate_gbps: Rate;
  modulation: string;
  max_reach_km: number;
}

export interface Snapshot {
  version: number;
  num_channels: number;
  nodes: NodeInfo[];
  links: LinkInfo[];
  services: Service[];
  alarms: Alarm[];
  alarm_history: Alarm[];
  events: NetEvent[];
  stats: Stats;
  rate_profiles: RateProfile[];
}

export interface PathCandidate {
  path: PathInfo;
  feasible: boolean;
  reason: string;
  channel: number | null;
}

export interface OperationResult {
  affected: string[];
  switched: string[];
  restored: string[];
  down: string[];
}

export interface TelemetrySample {
  ts: number;
  osnr_db: number;
  rx_power_dbm: number;
  utilization: number;
}

export interface ServiceRequest {
  src: string;
  dst: string;
  rate_gbps: Rate;
  protection: ProtectionType;
  name?: string;
}

/** What the map should highlight. */
export type Selection =
  | { kind: "none" }
  | { kind: "link"; id: string }
  | { kind: "service"; id: string };
