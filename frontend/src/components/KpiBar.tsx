import { pct } from "../format";
import type { Stats } from "../types";

export function KpiBar({ stats }: { stats: Stats }) {
  const s = stats.services_by_status;
  const a = stats.alarms_by_severity;
  return (
    <div className="kpis" role="group" aria-label="Network KPIs">
      <div className="kpi">
        <span className="kpi-label">Services</span>
        <span className="kpi-value">{stats.services_total}</span>
        <span className="kpi-sub">
          <span className="text-ok">{s.UP} up</span>
          {s.DEGRADED > 0 && <span className="text-warn"> · {s.DEGRADED} unprot.</span>}
          {s.DOWN > 0 && <span className="text-crit"> · {s.DOWN} down</span>}
        </span>
      </div>
      <div className="kpi">
        <span className="kpi-label">Active alarms</span>
        <span className={`kpi-value ${a.CRITICAL ? "text-crit" : a.MAJOR ? "text-warn" : ""}`}>
          {a.CRITICAL + a.MAJOR + a.MINOR + a.WARNING}
        </span>
        <span className="kpi-sub">
          {a.CRITICAL} crit · {a.MAJOR} maj · {a.MINOR} min
        </span>
      </div>
      <div className="kpi">
        <span className="kpi-label">Spectrum used</span>
        <span className="kpi-value">{pct(stats.network_utilization, 1)}</span>
        <span className="kpi-sub">{stats.links_down} fiber(s) down</span>
      </div>
      <div className="kpi">
        <span className="kpi-label">Carried capacity</span>
        <span className="kpi-value">{stats.capacity_tbps.toFixed(1)} Tb/s</span>
        <span className="kpi-sub">across live services</span>
      </div>
      <div className="kpi">
        <span className="kpi-label">Blocking</span>
        <span className="kpi-value">{pct(stats.blocking_probability, 1)}</span>
        <span className="kpi-sub">
          {stats.blocked_total}/{stats.requests_total} requests
        </span>
      </div>
    </div>
  );
}
