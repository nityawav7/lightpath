import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Snapshot } from "./types";

export type ConnectionState = "connecting" | "live" | "offline";

/**
 * Keeps an always-fresh copy of the network snapshot.
 * Primary channel: WebSocket push. Fallback: REST polling while the socket is
 * down, with exponential back-off reconnects.
 */
export function useNetwork() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const latestVersion = useRef(-1);

  const accept = useCallback((snap: Snapshot) => {
    // Telemetry ticks reuse the same version, so accept equal versions too.
    if (snap.version >= latestVersion.current) {
      latestVersion.current = snap.version;
      setSnapshot(snap);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      accept(await api.snapshot());
    } catch {
      /* the socket/poller will retry */
    }
  }, [accept]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let reconnectTimer: number | undefined;
    let pollTimer: number | undefined;
    let disposed = false;

    const startPolling = () => {
      if (pollTimer !== undefined) return;
      pollTimer = window.setInterval(() => void refresh(), 5000);
    };
    const stopPolling = () => {
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
      pollTimer = undefined;
    };

    const connect = () => {
      if (disposed) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws`);
      ws.onopen = () => {
        retry = 0;
        setConnection("live");
        stopPolling();
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(ev.data) as { type: string; data: Snapshot };
          if (msg.type === "snapshot") accept(msg.data);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        setConnection("offline");
        startPolling();
        const delay = Math.min(10_000, 1000 * 2 ** retry++);
        reconnectTimer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };

    void refresh();
    connect();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      stopPolling();
      ws?.close();
    };
  }, [accept, refresh]);

  return { snapshot, connection, refresh };
}
