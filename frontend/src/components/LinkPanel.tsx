import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { pct, serviceColor } from "../format";
import type { LinkInfo, TelemetrySample } from "../types";
import { Sparkline } from "./Sparkline";

interface Props {
  link: LinkInfo;
  version: number;
  busy: boolean;
  onFail: (id: string) => void;
  onRepair: (id: string) => void;
  onSelectService: (id: string) => void;
  onClose: () => void;
}

const OSNR_THRESHOLD = 15;

export function LinkPanel({ link, version, busy, onFail, onRepair, onSelectService, onClose }: Props) {
  const [samples, setSamples] = useState<TelemetrySample[]>([]);
  const ref = useRef<HTMLElement>(null);

  // Bring the panel into view when a different fiber is selected.
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [link.id]);

  // Re-fetch PM history whenever a new snapshot arrives (every telemetry tick).
  useEffect(() => {
    let cancelled = false;
    api
      .telemetry(link.id)
      .then((s) => !cancelled && setSamples(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [link.id, version, link.osnr_db]);

  const down = link.status === "DOWN";
  const up = samples.filter((s) => s.osnr_db > 0);

  return (
    <section ref={ref} className="card link-panel" aria-label={`Fiber ${link.id}`}>
      <header className="card-head">
        <div>
          <h2>
            Fiber {link.id}{" "}
            <span className={`badge ${down ? "badge-crit" : "badge-ok"}`}>{down ? "DOWN · LOS" : "IN SERVICE"}</span>
          </h2>
          <p className="muted">
            {link.a} ⇄ {link.b} · {link.length_km} km · {Math.ceil(link.length_km / 80)} amplified spans ·{" "}
            {link.latency_ms.toFixed(2)} ms one-way
          </p>
        </div>
        <div className="row gap">
          {down ? (
            <button className="btn btn-ok" disabled={busy} onClick={() => onRepair(link.id)}>
              Repair fiber
            </button>
          ) : (
            <button className="btn btn-danger" disabled={busy} onClick={() => onFail(link.id)}>
              ✂ Cut fiber
            </button>
          )}
          <button className="btn btn-ghost icon" onClick={onClose} aria-label="Close fiber details">
            ✕
          </button>
        </div>
      </header>

      <div className="link-grid">
        <div>
          <div className="spectrum-head">
            <span>
              DWDM spectrum · {link.used_channels}/{link.channels.length} λ used ({pct(link.utilization)})
            </span>
            <span className="muted small">C-band, 100 GHz grid</span>
          </div>
          <div className="spectrum" role="list">
            {link.channels.map((owner, i) => (
              <button
                key={i}
                role="listitem"
                className={`lambda ${owner ? "used" : ""}`}
                style={owner ? { background: serviceColor(owner) } : undefined}
                title={
                  owner
                    ? `λ${i + 1} · ${(191.3 + i * 0.1).toFixed(2)} THz · ${owner}`
                    : `λ${i + 1} · ${(191.3 + i * 0.1).toFixed(2)} THz · free`
                }
                onClick={() => owner && onSelectService(owner)}
                disabled={!owner}
              >
                <span className="sr-only">{owner ?? "free"}</span>
              </button>
            ))}
          </div>
          <div className="spectrum-axis muted small">
            <span>191.30 THz</span>
            <span>{(191.3 + (link.channels.length - 1) * 0.1).toFixed(2)} THz</span>
          </div>
        </div>
        <div className="sparks">
          <Sparkline
            label="OSNR"
            unit="dB"
            values={up.map((s) => s.osnr_db)}
            threshold={OSNR_THRESHOLD}
            min={10}
          />
          <Sparkline
            label="Rx power"
            unit="dBm"
            values={up.map((s) => s.rx_power_dbm)}
            color="var(--protect)"
          />
        </div>
      </div>
    </section>
  );
}
