import type {
  Alarm,
  OperationResult,
  PathCandidate,
  Rate,
  Service,
  ServiceRequest,
  Snapshot,
  TelemetrySample,
} from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the controller. Check your connection.");
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const data: unknown = await res.json();
      if (data && typeof data === "object" && "detail" in data) {
        const d = (data as { detail: unknown }).detail;
        if (typeof d === "string") detail = d;
        else if (Array.isArray(d) && d[0] && typeof d[0] === "object" && "msg" in d[0]) {
          detail = String((d[0] as { msg: unknown }).msg);
        }
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  snapshot: () => request<Snapshot>("GET", "/api/snapshot"),
  createService: (req: ServiceRequest) => request<Service>("POST", "/api/services", req),
  deleteService: (id: string) => request<void>("DELETE", `/api/services/${encodeURIComponent(id)}`),
  computePaths: (src: string, dst: string, rate_gbps: Rate) =>
    request<PathCandidate[]>("POST", "/api/paths/compute", { src, dst, rate_gbps }),
  failLink: (id: string) =>
    request<OperationResult>("POST", `/api/links/${encodeURIComponent(id)}/fail`),
  repairLink: (id: string) =>
    request<OperationResult>("POST", `/api/links/${encodeURIComponent(id)}/repair`),
  telemetry: (id: string) =>
    request<TelemetrySample[]>("GET", `/api/links/${encodeURIComponent(id)}/telemetry`),
  ackAlarm: (id: number) => request<Alarm>("POST", `/api/alarms/${id}/ack`),
  traffic: (count: number) =>
    request<{ provisioned: number; blocked: number; reasons: Record<string, number> }>(
      "POST",
      "/api/simulate/traffic",
      { count },
    ),
  reset: () => request<void>("POST", "/api/reset"),
};
