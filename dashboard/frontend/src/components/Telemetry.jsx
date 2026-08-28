import { useState } from "react";
import Terminal from "./Terminal.jsx";
import { AGENTS } from "../api.js";

const AGENT_NAME = {
  video: "Video Creation",
  music: "Music Generation",
  mixing: "Mix & Sync",
  subtitle: "Titles & Description",
  exporting: "Export",
  thumbnail: "Thumbnail",
};

function health(online, job, failures, history) {
  if (online === false) return ["off", "● Offline"];
  if (failures.length) return ["warn", "⚠ Attention"];
  if (job) return ["ok", "+ Healthy"];
  const last = history[0];
  if (last && last.status === "failed") return ["warn", "⚠ Attention"];
  return ["ok", "+ Healthy"];
}

// Row label + bar state per agent: done 100%, active NN%, the next pending
// agent reads "Queued", the rest "Waiting"; everything idle when no job runs.
function rowsFor(job) {
  const prog = job?.progress || {};
  let queuedGiven = false;
  return AGENTS.map((a) => {
    const p = prog[a.key] || { state: "idle", pct: 0 };
    let label, cls;
    if (!job) {
      label = "Idle"; cls = "idle";
    } else if (p.state === "done") {
      label = "✓ Done"; cls = "done";
    } else if (p.state === "failed") {
      label = "✕ Failed"; cls = "failed";
    } else if (p.state === "active") {
      label = `${p.pct}%`; cls = "active";
    } else if (!queuedGiven) {
      queuedGiven = true;
      label = "Queued"; cls = "queued";
    } else {
      label = "Waiting"; cls = "waiting";
    }
    return { key: a.key, name: AGENT_NAME[a.key], pct: p.pct, label, cls };
  });
}

export default function Telemetry({ online, job, failures, history, lines }) {
  const [open, setOpen] = useState(true);
  const [showLogs, setShowLogs] = useState(false);
  const [hCls, hLabel] = health(online, job, failures, history);
  const rows = rowsFor(job);

  return (
    <section className="panel tele-panel">
      <button className="tele-head" onClick={() => setOpen(!open)}>
        <span className="panel-title tele-title">〜 TELEMETRY</span>
        <span className="tele-chev">{open ? "⌃" : "⌄"}</span>
      </button>

      {open && (
        <>
          <div className="tele-health-row">
            <span>Pipeline Health</span>
            <span className={"health-badge " + hCls}>{hLabel}</span>
          </div>

          <div className="tele-rows">
            {rows.map((r) => (
              <div className="tele-row" key={r.key}>
                <span className="tele-name">{r.name}</span>
                <span className="tele-bar">
                  <span className={"tele-fill " + r.cls} style={{ width: r.pct + "%" }} />
                </span>
                <span className={"tele-val " + r.cls}>{r.label}</span>
              </div>
            ))}
          </div>

          <button className="btn tele-logs-btn" onClick={() => setShowLogs(!showLogs)}>
            {showLogs ? "▴ HIDE LOGS" : "＞_ VIEW FULL LOGS"}
          </button>
          {showLogs && <Terminal lines={lines} />}
        </>
      )}
    </section>
  );
}
