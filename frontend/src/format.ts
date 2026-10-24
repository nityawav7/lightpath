export function timeAgo(tsSeconds: number, now = Date.now()): string {
  const s = Math.max(0, Math.round(now / 1000 - tsSeconds));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function clock(tsSeconds: number): string {
  return new Date(tsSeconds * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;

/** Stable, distinct-ish colour per service id for the spectrum view. */
export function serviceColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const hue = (h * 137.508) % 360;
  return `hsl(${hue.toFixed(0)} 70% 62%)`;
}

export function utilizationColor(u: number): string {
  if (u >= 0.8) return "var(--crit)";
  if (u >= 0.5) return "var(--warn)";
  if (u > 0) return "var(--ok)";
  return "var(--idle)";
}

export const route = (nodes: string[]) => nodes.join(" › ");
