import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { AlarmsPanel } from "./components/AlarmsPanel";
import { EventsPanel } from "./components/EventsPanel";
import { KpiBar } from "./components/KpiBar";
import { LinkPanel } from "./components/LinkPanel";
import { ProvisionForm } from "./components/ProvisionForm";
import { ServiceDetail, ServicesPanel } from "./components/ServicesPanel";
import { Toasts, type Toast } from "./components/Toasts";
import { TopologyMap } from "./components/TopologyMap";
import type { OperationResult, PathInfo, Selection } from "./types";
import { useNetwork } from "./useNetwork";

type Tab = "provision" | "services" | "alarms" | "events";

function summarize(prefix: string, r: OperationResult): string {
  const parts = [`${r.affected.length} service(s) affected`];
  if (r.switched.length) parts.push(`${r.switched.length} protection switch`);
  if (r.restored.length) parts.push(`${r.restored.length} restored`);
  if (r.down.length) parts.push(`${r.down.length} down`);
  return `${prefix}: ${parts.join(" · ")}`;
}

export default function App() {
  const { snapshot, connection, refresh } = useNetwork();
  const [tab, setTab] = useState<Tab>("provision");
  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [endpoints, setEndpoints] = useState({ src: "", dst: "" });
  const [preview, setPreview] = useState<PathInfo | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const toastId = useRef(0);

  const toast = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t.slice(-3), { id, kind, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const run = useCallback(
    async <T,>(fn: () => Promise<T>, onOk?: (v: T) => void) => {
      setBusy(true);
      try {
        const v = await fn();
        onOk?.(v);
        void refresh();
      } catch (e) {
        toast("error", e instanceof ApiError ? e.message : "Request failed");
      } finally {
        setBusy(false);
      }
    },
    [refresh, toast],
  );

  const links = snapshot?.links ?? [];
  const services = snapshot?.services ?? [];
  const selectedLink =
    selection.kind === "link" ? (links.find((l) => l.id === selection.id) ?? null) : null;
  const selectedService =
    selection.kind === "service" ? (services.find((s) => s.id === selection.id) ?? null) : null;

  // Drop a selection if the object disappeared (e.g. deleted, or after reset).
  useEffect(() => {
    if (!snapshot) return;
    if (selection.kind === "service" && !selectedService) setSelection({ kind: "none" });
    if (selection.kind === "link" && !selectedLink) setSelection({ kind: "none" });
  }, [snapshot, selection, selectedService, selectedLink]);

  const alarmedLinks = useMemo(
    () => new Set((snapshot?.alarms ?? []).filter((a) => a.resource.includes("-")).map((a) => a.resource)),
    [snapshot?.alarms],
  );

  const selectNode = (id: string) => {
    setTab("provision");
    setPreview(null);
    setEndpoints(({ src, dst }) => {
      if (!src || (src && dst)) return { src: id, dst: "" };
      if (id === src) return { src, dst };
      return { src, dst: id };
    });
  };

  const selectService = (id: string) => {
    setSelection({ kind: "service", id });
    setTab("services");
    setPreview(null);
  };
  const selectLink = (id: string) => {
    setSelection({ kind: "link", id });
    setPreview(null);
  };
  const selectResource = (res: string) => (res.startsWith("SVC-") ? selectService(res) : selectLink(res));

  const failLink = (id: string) =>
    run(() => api.failLink(id), (r) => toast(r.down.length ? "error" : "warn", summarize(`Fiber cut on ${id}`, r)));
  const repairLink = (id: string) =>
    run(() => api.repairLink(id), (r) => toast("ok", summarize(`Fiber ${id} repaired`, r)));

  if (!snapshot) {
    return (
      <div className="boot">
        <div className="boot-card">
          <div className="spinner" aria-hidden="true" />
          <h1>LightPath</h1>
          <p className="muted">
            {connection === "offline"
              ? "Waking up the controller… (free hosting sleeps when idle, this can take ~30 s)"
              : "Connecting to the network controller…"}
          </p>
        </div>
      </div>
    );
  }

  const alarmCount = snapshot.alarms.length;
  const unacked = snapshot.alarms.filter((a) => !a.acknowledged && a.severity === "CRITICAL").length;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
            <path d="M5 22 L13 12 L19 18 L27 8" fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="13" cy="12" r="2.6" fill="var(--protect)" />
            <circle cx="19" cy="18" r="2.6" fill="var(--protect)" />
          </svg>
          <div>
            <h1>LightPath</h1>
            <span className="muted small">Optical Network Controller</span>
          </div>
        </div>
        <KpiBar stats={snapshot.stats} />
        <div className={`conn conn-${connection}`} title="Real-time connection to the controller">
          <span className="dot" /> {connection === "live" ? "Live" : connection === "offline" ? "Reconnecting" : "Connecting"}
        </div>
      </header>

      <main className="layout">
        <section className="map-col">
          <div className="map-toolbar">
            <div className="legend" aria-label="Legend">
              <span><i className="lg lg-ok" /> &lt;50%</span>
              <span><i className="lg lg-warn" /> 50–80%</span>
              <span><i className="lg lg-crit" /> &gt;80% / cut</span>
              <span><i className="lg lg-work" /> working</span>
              <span><i className="lg lg-prot" /> protection</span>
            </div>
            <div className="row gap">
              <button
                className="btn btn-sm"
                disabled={busy}
                onClick={() =>
                  run(() => api.traffic(20), (r) =>
                    toast(r.blocked ? "warn" : "ok", `Offered 20 demands: ${r.provisioned} provisioned, ${r.blocked} blocked`),
                  )
                }
              >
                + 20 random demands
              </button>
              <button
                className="btn btn-sm btn-ghost"
                disabled={busy}
                onClick={() =>
                  run(() => api.reset(), () => {
                    setSelection({ kind: "none" });
                    toast("info", "Network reset to reference topology");
                  })
                }
              >
                Reset
              </button>
            </div>
          </div>
          <div className="map-wrap">
            <TopologyMap
              nodes={snapshot.nodes}
              links={links}
              selectedLinkId={selectedLink?.id ?? null}
              selectedService={selectedService}
              previewPath={preview}
              endpoints={endpoints}
              alarmedLinks={alarmedLinks}
              onSelectLink={selectLink}
              onSelectNode={selectNode}
            />
            {!selectedLink && (
              <p className="map-hint muted small">
                Click a fiber to inspect its spectrum or cut it · click two cities to route a service
              </p>
            )}
          </div>
          {selectedLink && (
            <LinkPanel
              link={selectedLink}
              version={snapshot.version}
              busy={busy}
              onFail={failLink}
              onRepair={repairLink}
              onSelectService={selectService}
              onClose={() => setSelection({ kind: "none" })}
            />
          )}
        </section>

        <aside className="side-col">
          <nav className="tabs" role="tablist">
            {(
              [
                ["provision", "Provision"],
                ["services", `Services (${services.length})`],
                ["alarms", `Alarms (${alarmCount})`],
                ["events", "Events"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={`tab ${tab === key ? "on" : ""}`}
                onClick={() => setTab(key)}
              >
                {label}
                {key === "alarms" && unacked > 0 && <span className="tab-badge">{unacked}</span>}
              </button>
            ))}
          </nav>

          <div className="tab-body">
            {tab === "provision" && (
              <ProvisionForm
                nodes={snapshot.nodes}
                rateProfiles={snapshot.rate_profiles}
                src={endpoints.src}
                dst={endpoints.dst}
                onEndpoints={(src, dst) => setEndpoints({ src, dst })}
                onPreview={setPreview}
                onProvisioned={(svc) => {
                  toast("ok", `${svc.id} provisioned on λ${(svc.working?.channel ?? 0) + 1} via ${svc.working?.path.nodes.join(" › ")}`);
                  setEndpoints({ src: "", dst: "" });
                  selectService(svc.id);
                  void refresh();
                }}
                onError={(m) => toast("error", m)}
              />
            )}
            {tab === "services" && (
              <>
                {selectedService && (
                  <ServiceDetail
                    svc={selectedService}
                    busy={busy}
                    onClose={() => setSelection({ kind: "none" })}
                    onDelete={(id) => run(() => api.deleteService(id), () => toast("info", `${id} deleted`))}
                  />
                )}
                <ServicesPanel
                  services={services}
                  selectedId={selectedService?.id ?? null}
                  onSelect={(id) => (id ? selectService(id) : setSelection({ kind: "none" }))}
                />
              </>
            )}
            {tab === "alarms" && (
              <AlarmsPanel
                alarms={snapshot.alarms}
                history={snapshot.alarm_history}
                onAck={(id) => run(() => api.ackAlarm(id))}
                onResource={selectResource}
              />
            )}
            {tab === "events" && (
              <EventsPanel events={snapshot.events} onService={selectService} onLink={selectLink} />
            )}
          </div>
        </aside>
      </main>
      <Toasts toasts={toasts} onDismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />
    </div>
  );
}
