import { clock } from "../format";
import type { NetEvent } from "../types";

interface Props {
  events: NetEvent[];
  onService: (id: string) => void;
  onLink: (id: string) => void;
}

export function EventsPanel({ events, onService, onLink }: Props) {
  return (
    <ul className="list events" aria-live="polite">
      {events.length === 0 && <li className="empty muted">No events yet.</li>}
      {events.map((e) => (
        <li key={e.id} className={`event lvl-${e.level}`}>
          <time className="muted small">{clock(e.ts)}</time>
          <div>
            <span className="kind">{e.kind.replace(/_/g, " ")}</span> {e.message}
            {(e.service_id || e.link_id) && (
              <span className="event-links">
                {e.service_id && (
                  <button className="linkish" onClick={() => onService(e.service_id!)}>
                    view service
                  </button>
                )}
                {e.link_id && (
                  <button className="linkish" onClick={() => onLink(e.link_id!)}>
                    view fiber
                  </button>
                )}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
