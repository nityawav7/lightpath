import { clock, timeAgo } from "../format";
import type { Alarm } from "../types";

interface Props {
  alarms: Alarm[];
  history: Alarm[];
  onAck: (id: number) => void;
  onResource: (resource: string) => void;
}

export function AlarmsPanel({ alarms, history, onAck, onResource }: Props) {
  return (
    <div className="alarms">
      {alarms.length === 0 ? (
        <div className="all-clear">
          <span className="dot status-UP" /> No active alarms. Network is healthy.
        </div>
      ) : (
        <ul className="list">
          {alarms.map((a) => (
            <li key={a.id} className={`alarm sev-${a.severity} ${a.acknowledged ? "acked" : ""}`}>
              <span className={`sev sev-${a.severity}`}>{a.severity}</span>
              <div className="li-main">
                <div className="li-title">
                  {a.type.replace(/_/g, " ")} ·{" "}
                  <button className="linkish" onClick={() => onResource(a.resource)}>
                    {a.resource}
                  </button>
                </div>
                <div className="li-sub muted">
                  {a.message} · {timeAgo(a.raised_at)}
                </div>
              </div>
              {a.acknowledged ? (
                <span className="muted small" title="Acknowledged">
                  ✓ ack
                </span>
              ) : (
                <button className="btn btn-sm" onClick={() => onAck(a.id)}>
                  Ack
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {history.length > 0 && (
        <details className="history">
          <summary>Recently cleared ({history.length})</summary>
          <ul className="list compact">
            {history.map((a) => (
              <li key={a.id} className="muted small">
                <span className={`sev sev-${a.severity} faded`}>{a.severity}</span> {a.type.replace(/_/g, " ")} ·{" "}
                {a.resource} · cleared {a.cleared_at ? clock(a.cleared_at) : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
