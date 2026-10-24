import { useMemo, useState } from "react";
import type { LinkInfo, NodeInfo, PathInfo, Service } from "../types";
import { pct, utilizationColor } from "../format";

const W = 800;
const H = 900;
const PAD = 70;
// Sites whose label would collide with a neighbour are labelled on the left.
const LABEL_LEFT = new Set(["BOM", "AMD"]);

interface Props {
  nodes: NodeInfo[];
  links: LinkInfo[];
  selectedLinkId: string | null;
  selectedService: Service | null;
  previewPath: PathInfo | null;
  endpoints: { src: string; dst: string };
  alarmedLinks: Set<string>;
  onSelectLink: (id: string) => void;
  onSelectNode: (id: string) => void;
}

type Point = { x: number; y: number };

/** Equirectangular projection fitted to the node bounding box. */
function useProjection(nodes: NodeInfo[]) {
  return useMemo(() => {
    const lats = nodes.map((n) => n.lat);
    const lons = nodes.map((n) => n.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
    const spanX = (maxLon - minLon) * k || 1;
    const spanY = maxLat - minLat || 1;
    const scale = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY);
    const offX = (W - spanX * scale) / 2;
    const offY = (H - spanY * scale) / 2;
    const pos = new Map<string, Point>();
    for (const n of nodes) {
      pos.set(n.id, {
        x: offX + (n.lon - minLon) * k * scale,
        y: offY + (maxLat - n.lat) * scale,
      });
    }
    return pos;
  }, [nodes]);
}

function pathPoints(path: PathInfo, pos: Map<string, Point>): string {
  return path.nodes
    .map((id) => pos.get(id))
    .filter((p): p is Point => !!p)
    .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
}

export function TopologyMap(props: Props) {
  const { nodes, links, selectedLinkId, selectedService, previewPath, endpoints } = props;
  const pos = useProjection(nodes);
  const [hoverLink, setHoverLink] = useState<string | null>(null);

  const working = selectedService?.working ?? null;
  const protection = selectedService?.protection_leg ?? null;
  const activeRole = selectedService?.active;

  return (
    <svg
      className="topology"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Optical network topology map"
    >
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--grid)" strokeWidth="1" />
        </pattern>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect width={W} height={H} fill="url(#grid)" />

      {/* Fibers */}
      {links.map((l) => {
        const a = pos.get(l.a);
        const b = pos.get(l.b);
        if (!a || !b) return null;
        const down = l.status === "DOWN";
        const selected = l.id === selectedLinkId;
        const hovered = l.id === hoverLink;
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        const color = down ? "var(--crit)" : utilizationColor(l.utilization);
        return (
          <g
            key={l.id}
            className="link"
            onClick={() => props.onSelectLink(l.id)}
            onMouseEnter={() => setHoverLink(l.id)}
            onMouseLeave={() => setHoverLink((h) => (h === l.id ? null : h))}
          >
            <title>
              {`${l.id} · ${l.length_km} km · ${l.used_channels}/${l.channels.length} λ (${pct(l.utilization)})${down ? " · DOWN" : ""}`}
            </title>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={22} />
            {selected && (
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--text)"
                strokeWidth={12}
                strokeOpacity={0.18}
                strokeLinecap="round"
              />
            )}
            <line
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={color}
              strokeWidth={hovered || selected ? 6 : 4}
              strokeDasharray={down ? "10 8" : undefined}
              strokeLinecap="round"
              opacity={down ? 0.9 : 0.85}
            />
            {props.alarmedLinks.has(l.id) && !down && (
              <circle cx={mid.x} cy={mid.y} r={5} className="pulse" fill="var(--warn)" />
            )}
            {down && (
              <g transform={`translate(${mid.x} ${mid.y})`} className="cut-marker">
                <circle r={11} fill="var(--bg)" stroke="var(--crit)" strokeWidth={2} />
                <path d="M -5 -5 L 5 5 M 5 -5 L -5 5" stroke="var(--crit)" strokeWidth={2.5} />
              </g>
            )}
            {(hovered || selected) && !down && (
              <text x={mid.x} y={mid.y - 10} className="link-label" textAnchor="middle">
                {l.length_km} km · {l.used_channels}/{l.channels.length}λ
              </text>
            )}
          </g>
        );
      })}

      {/* Path overlays */}
      {previewPath && (
        <polyline
          points={pathPoints(previewPath, pos)}
          className="path-preview"
          fill="none"
        />
      )}
      {protection && (
        <polyline
          points={pathPoints(protection.path, pos)}
          className={`path-overlay protection ${activeRole === "protection" ? "active" : ""}`}
          fill="none"
          filter={activeRole === "protection" ? "url(#glow)" : undefined}
        />
      )}
      {working && (
        <polyline
          points={pathPoints(working.path, pos)}
          className={`path-overlay working ${activeRole === "working" ? "active" : ""}`}
          fill="none"
          filter={activeRole === "working" ? "url(#glow)" : undefined}
        />
      )}

      {/* ROADM sites */}
      {nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const isEndpoint = n.id === endpoints.src || n.id === endpoints.dst;
        const inService =
          selectedService && (n.id === selectedService.src || n.id === selectedService.dst);
        const labelLeft = LABEL_LEFT.has(n.id) || p.x > W - 140;
        return (
          <g
            key={n.id}
            className="node"
            transform={`translate(${p.x} ${p.y})`}
            onClick={() => props.onSelectNode(n.id)}
          >
            <title>{`${n.name} (${n.id}) · degree ${n.degree} ROADM · click to use as endpoint`}</title>
            <circle r={18} fill="transparent" />
            <circle
              r={isEndpoint || inService ? 12 : 10}
              className={`node-dot ${isEndpoint ? "endpoint" : ""} ${inService ? "in-service" : ""}`}
            />
            <text
              x={labelLeft ? -16 : 16}
              y={-2}
              className="node-id"
              textAnchor={labelLeft ? "end" : "start"}
            >
              {n.id}
            </text>
            <text
              x={labelLeft ? -16 : 16}
              y={13}
              className="node-name"
              textAnchor={labelLeft ? "end" : "start"}
            >
              {n.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
