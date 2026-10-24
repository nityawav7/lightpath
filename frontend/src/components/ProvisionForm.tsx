import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { route } from "../format";
import type { NodeInfo, PathCandidate, PathInfo, ProtectionType, Rate, RateProfile, Service } from "../types";

interface Props {
  nodes: NodeInfo[];
  rateProfiles: RateProfile[];
  src: string;
  dst: string;
  onEndpoints: (src: string, dst: string) => void;
  onPreview: (p: PathInfo | null) => void;
  onProvisioned: (svc: Service) => void;
  onError: (msg: string) => void;
}

export function ProvisionForm(props: Props) {
  const { nodes, rateProfiles, src, dst } = props;
  const [rate, setRate] = useState<Rate>(100);
  const [protection, setProtection] = useState<ProtectionType>("NONE");
  const [name, setName] = useState("");
  const [candidates, setCandidates] = useState<PathCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);

  const valid = src && dst && src !== dst;
  const reset = () => {
    setCandidates(null);
    props.onPreview(null);
  };

  const compute = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      const c = await api.computePaths(src, dst, rate);
      setCandidates(c);
      props.onPreview(c.find((x) => x.feasible)?.path ?? c[0]?.path ?? null);
    } catch (e) {
      props.onError(e instanceof ApiError ? e.message : "Path computation failed");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      const svc = await api.createService({
        src,
        dst,
        rate_gbps: rate,
        protection,
        name: name.trim() || undefined,
      });
      setName("");
      reset();
      props.onProvisioned(svc);
    } catch (err) {
      props.onError(err instanceof ApiError ? `Blocked: ${err.message}` : "Provisioning failed");
    } finally {
      setBusy(false);
    }
  };

  const sorted = [...nodes].sort((a, b) => a.name.localeCompare(b.name));
  const profile = rateProfiles.find((p) => p.rate_gbps === rate);

  return (
    <form className="card provision" onSubmit={submit}>
      <header className="card-head">
        <h2>Provision wavelength service</h2>
      </header>
      <p className="muted small hint">Tip: click two cities on the map to pick endpoints.</p>
      <div className="field-row">
        <label className="field">
          <span>A-end</span>
          <select
            value={src}
            onChange={(e) => {
              props.onEndpoints(e.target.value, dst);
              reset();
            }}
          >
            <option value="">Select…</option>
            {sorted.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name} ({n.id})
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-ghost icon swap"
          aria-label="Swap endpoints"
          onClick={() => {
            props.onEndpoints(dst, src);
            reset();
          }}
        >
          ⇄
        </button>
        <label className="field">
          <span>Z-end</span>
          <select
            value={dst}
            onChange={(e) => {
              props.onEndpoints(src, e.target.value);
              reset();
            }}
          >
            <option value="">Select…</option>
            {sorted.map((n) => (
              <option key={n.id} value={n.id} disabled={n.id === src}>
                {n.name} ({n.id})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="field">
        <span>Line rate</span>
        <div className="segmented" role="radiogroup" aria-label="Line rate">
          {rateProfiles.map((p) => (
            <button
              type="button"
              key={p.rate_gbps}
              role="radio"
              aria-checked={rate === p.rate_gbps}
              className={rate === p.rate_gbps ? "on" : ""}
              onClick={() => {
                setRate(p.rate_gbps);
                reset();
              }}
            >
              {p.rate_gbps}G
            </button>
          ))}
        </div>
        {profile && (
          <span className="muted small">
            {profile.modulation} · max reach {profile.max_reach_km.toLocaleString()} km
          </span>
        )}
      </div>

      <div className="field">
        <span>Protection</span>
        <div className="segmented" role="radiogroup" aria-label="Protection">
          {(["NONE", "1+1"] as const).map((p) => (
            <button
              type="button"
              key={p}
              role="radio"
              aria-checked={protection === p}
              className={protection === p ? "on" : ""}
              onClick={() => setProtection(p)}
            >
              {p === "NONE" ? "Unprotected" : "1+1 protected"}
            </button>
          ))}
        </div>
        <span className="muted small">
          {protection === "1+1"
            ? "Working + link-disjoint protection path, hitless switch on fiber cut."
            : "Single path, re-routed by restoration after a fiber cut."}
        </span>
      </div>

      <label className="field">
        <span>Service name (optional)</span>
        <input
          value={name}
          maxLength={80}
          placeholder="e.g. DC interconnect Mumbai–Chennai"
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div className="row gap">
        <button type="button" className="btn" disabled={!valid || busy} onClick={compute}>
          Compute routes
        </button>
        <button type="submit" className="btn btn-primary grow" disabled={!valid || busy}>
          {busy ? "Working…" : "Provision service"}
        </button>
      </div>

      {candidates && (
        <ol className="candidates">
          {candidates.length === 0 && <li className="muted">No physical route available.</li>}
          {candidates.map((c, i) => (
            <li
              key={c.path.links.join()}
              className={c.feasible ? "ok" : "bad"}
              onMouseEnter={() => props.onPreview(c.path)}
            >
              <div className="cand-route">
                <strong>#{i + 1}</strong> {route(c.path.nodes)}
              </div>
              <div className="muted small">
                {c.path.length_km.toLocaleString()} km · {c.path.latency_ms.toFixed(2)} ms ·{" "}
                {c.path.hops} hops ·{" "}
                {c.feasible ? (
                  <span className="text-ok">λ{(c.channel ?? 0) + 1} available</span>
                ) : (
                  <span className="text-crit">{c.reason}</span>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </form>
  );
}
