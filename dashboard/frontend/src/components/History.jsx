import { useState } from "react";
import Chip from "./Chip.jsx";
import { AGENTS } from "../api.js";

const CHIP = {
  done: ["chip-uploaded", "✅"],
  failed: ["chip-failed", "✕"],
  cancelled: ["chip-missing", "⊘"],
  running: ["chip-active", "◉"],
  queued: ["chip-pending", "⧗"],
};

const AGENT_LABEL = Object.fromEntries(AGENTS.map((a) => [a.key, `${a.icon} ${a.label}`]));
const STEP_ICON = { active: "◉", done: "✓", failed: "✕" };

// Older job records predate the steps timeline — rebuild it from their log.
function stepsOf(job) {
  if (job.steps?.length) return job.steps;
  const out = [];
  let topic = null;
  // Markers may share a line with other output, so match rather than split.
  const re = /::agent::(\w+)::(active|done|failed)\b/;
  for (const line of job.log || []) {
    if (line.startsWith("::topic::")) topic = line.split("::topic::")[1].trim();
    const m = re.exec(line);
    if (!m) continue;
    const [, name, state] = m;
    if (state === "active") out.push({ agent: name, topic, state: "active", secs: null });
    else {
      const open = [...out].reverse().find((s) => s.agent === name && s.state === "active");
      if (open) open.state = state;
      else out.push({ agent: name, topic, state, secs: null });
    }
  }
  return out;
}

function Row({ j, expandable, onRetry }) {
  const [open, setOpen] = useState(false);
  const [cls, icon] = CHIP[j.status] || ["chip-missing", "·"];
  const when = (j.finished_at || j.started_at || j.created_at || "").replace("T", " ");
  const results = Object.entries(j.results || {});
  const fails = results.filter(([, r]) => r.status === "failed");
  const steps = expandable ? stepsOf(j) : [];

  return (
    <div className={"h-item" + (open ? " open" : "")}>
      <button
        className="h-row"
        onClick={() => expandable && setOpen(!open)}
        disabled={!expandable}
      >
        {expandable && <span className="h-chev">{open ? "▾" : "▸"}</span>}
        <Chip cls={cls}>{icon + " " + j.status.toUpperCase()}</Chip>
        <span className="h-when">{when}</span>
        <span className="h-label">{j.label}</span>
        <span className="muted">
          {results
            .map(([k, r]) =>
              `${r.status === "ok" ? "✅" : r.status === "failed" ? "✕" : "◉"} ${k}`)
            .join("  ")}
        </span>
      </button>

      {open && (
        <div className="h-detail">
          {fails.length > 0 && (
            <div className="h-fail-box">
              <div className="h-fail-title">✕ WHAT FAILED</div>
              {fails.map(([k, r]) => (
                <div className="h-fail-item" key={k}>
                  <span className="fail-key">{k}</span>
                  <span className="h-fail-msg">{r.error || "unknown error"}</span>
                </div>
              ))}
              <button
                className="btn btn-mini btn-primary"
                onClick={() => onRetry(fails.map(([k]) => k))}
              >
                ⟳ RETRY {fails.length > 1 ? `THESE ${fails.length}` : "THIS TOPIC"}
              </button>
            </div>
          )}

          <div className="h-steps-title">PIPELINE STEPS</div>
          {!steps.length && <div className="empty">No step detail recorded for this job.</div>}
          <ol className="h-steps">
            {steps.map((s, i) => (
              <li key={i} className={"h-step " + s.state}>
                <span className="h-step-icon">{STEP_ICON[s.state] || "·"}</span>
                <span className="h-step-name">{AGENT_LABEL[s.agent] || s.agent}</span>
                {s.topic && <span className="h-step-topic">{s.topic}</span>}
                <span className="h-step-secs">
                  {s.secs != null ? `${s.secs}s` : s.state === "active" ? "running…" : ""}
                </span>
              </li>
            ))}
          </ol>

          {j.log?.length > 0 && (
            <details className="h-log">
              <summary>Raw log ({j.log.length} lines)</summary>
              <pre className="terminal">{j.log.map((l) => "» " + l).join("\n")}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default function History({ job, queue, history, limit = 12, expandable = false, onRetry }) {
  const rows = [
    ...queue.map((j) => ({ ...j, status: "queued" })),
    ...(job ? [{ ...job, status: "running" }] : []),
    ...history.slice(0, limit),
  ];
  return (
    <div className="history">
      {!rows.length && <div className="empty">No jobs yet.</div>}
      {rows.map((j) => (
        <Row
          key={j.id}
          j={j}
          expandable={expandable && j.status !== "queued"}
          onRetry={onRetry}
        />
      ))}
    </div>
  );
}
