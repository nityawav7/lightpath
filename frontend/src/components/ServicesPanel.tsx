import { useMemo, useState } from "react";
import { route, serviceColor, timeAgo } from "../format";
import type { Leg, Service, ServiceStatus } from "../types";

interface Props {
  services: Service[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const FILTERS: ("ALL" | ServiceStatus)[] = ["ALL", "UP", "DEGRADED", "DOWN"];

function LegRow({ role, leg, active }: { role: string; leg: Leg | null; active: boolean }) {
  return (
    <div className={`leg ${role} ${active ? "active" : ""}`}>
      <div className="leg-head">
        <span className="leg-role">{role}</span>
        {leg && active && <span className="badge badge-accent">carrying traffic</span>}
        {leg && !active && <span className="badge">standby</span>}
        {!leg && <span className="badge badge-crit">lost</span>}
      </div>
      {leg ? (
        <>
          <div className="leg-route">{route(leg.path.nodes)}</div>
          <div className="muted small">
            λ{leg.channel + 1} @ {leg.frequency_thz.toFixed(2)} THz · {leg.path.length_km.toLocaleString()} km ·{" "}
            {leg.path.latency_ms.toFixed(2)} ms · {leg.path.hops} hops
          </div>
        </>
      ) : (
        <div className="muted small">No restorable route right now. Will retry on repair.</div>
      )}
    </div>
  );
}

export function ServiceDetail({ svc, busy, onDelete, onClose }: { svc: Service; busy: boolean; onDelete: (id: string) => void; onClose: () => void }) {
  return (
    <section className="card service-detail" aria-label={`Service ${svc.id}`}>
      <header className="card-head">
        <div>
          <h2>
            <span className="swatch" style={{ background: serviceColor(svc.id) }} />
            {svc.id} <span className={`badge status-${svc.status}`}>{svc.status}</span>
          </h2>
          <p className="muted">{svc.name}</p>
        </div>
        <button className="btn btn-ghost icon" onClick={onClose} aria-label="Close service details">
          ✕
        </button>
      </header>
      <dl className="facts">
        <div>
          <dt>Endpoints</dt>
          <dd>
            {svc.src} ⇄ {svc.dst}
          </dd>
        </div>
        <div>
          <dt>Rate</dt>
          <dd>{svc.rate_gbps}G</dd>
        </div>
        <div>
          <dt>Modulation</dt>
          <dd>{svc.modulation}</dd>
        </div>
        <div>
          <dt>Protection</dt>
          <dd>{svc.protection === "1+1" ? "1+1 + restoration" : "Restoration only"}</dd>
        </div>
        <div>
          <dt>Switchovers</dt>
          <dd>{svc.switchovers}</dd>
        </div>
        <div>
          <dt>Restorations</dt>
          <dd>{svc.restorations}</dd>
        </div>
      </dl>
      <LegRow role="working" leg={svc.working} active={svc.active === "working" && !!svc.working} />
      {svc.protection === "1+1" && (
        <LegRow
          role="protection"
          leg={svc.protection_leg}
          active={svc.active === "protection" && !!svc.protection_leg}
        />
      )}
      <div className="row space muted small">
        <span>Created {timeAgo(svc.created_at)}</span>
        <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => onDelete(svc.id)}>
          Delete service
        </button>
      </div>
    </section>
  );
}

export function ServicesPanel({ services, selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [query, setQuery] = useState("");

  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: services.length, UP: 0, DEGRADED: 0, DOWN: 0 };
    for (const s of services) c[s.status] = (c[s.status] ?? 0) + 1;
    return c;
  }, [services]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const order: Record<ServiceStatus, number> = { DOWN: 0, DEGRADED: 1, UP: 2 };
    return services
      .filter((s) => filter === "ALL" || s.status === filter)
      .filter(
        (s) =>
          !q ||
          s.id.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.src.toLowerCase() === q ||
          s.dst.toLowerCase() === q,
      )
      .sort((a, b) => order[a.status] - order[b.status] || b.created_at - a.created_at);
  }, [services, filter, query]);

  return (
    <div className="services">
      <div className="toolbar">
        <div className="chips">
          {FILTERS.map((f) => (
            <button key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
              {f === "ALL" ? "All" : f} <span>{counts[f] ?? 0}</span>
            </button>
          ))}
        </div>
        <input
          className="search"
          placeholder="Search id, name or city code"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search services"
        />
      </div>
      <ul className="list">
        {shown.length === 0 && <li className="empty muted">No services match.</li>}
        {shown.map((s) => (
          <li key={s.id}>
            <button
              className={`list-item ${s.id === selectedId ? "selected" : ""}`}
              onClick={() => onSelect(s.id === selectedId ? null : s.id)}
            >
              <span className={`dot status-${s.status}`} aria-label={s.status} />
              <span className="li-main">
                <span className="li-title">
                  {s.id} <span className="muted">· {s.src} ⇄ {s.dst}</span>
                </span>
                <span className="li-sub muted">{s.name}</span>
              </span>
              <span className="li-tags">
                <span className="tag">{s.rate_gbps}G</span>
                {s.protection === "1+1" && <span className="tag tag-protect">1+1</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
