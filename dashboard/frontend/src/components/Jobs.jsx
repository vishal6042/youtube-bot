import { useState } from "react";
import Chip from "./Chip.jsx";
import { AGENTS } from "../api.js";

const SHOWN = 3;

const FILTERS = [
  ["all", "ALL"],
  ["running", "◉ IN PROGRESS"],
  ["done", "✅ COMPLETED"],
  ["failed", "✕ FAILED"],
];

const STATUS_CHIP = {
  running: ["chip-active", "◉ RUNNING"],
  queued: ["chip-pending", "⧗ QUEUED"],
  done: ["chip-uploaded", "✅ COMPLETED"],
  failed: ["chip-failed", "✕ FAILED"],
  cancelled: ["chip-missing", "⊘ CANCELLED"],
};

function fmtElapsed(from, to) {
  if (!from) return "";
  const end = to ? new Date(to).getTime() : Date.now();
  const s = Math.max(0, Math.floor((end - new Date(from).getTime()) / 1000));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function failedKeys(j) {
  return Object.entries(j.results || {})
    .filter(([, r]) => r.status === "failed")
    .map(([k]) => k);
}

export default function Jobs({ job, queue, history, onAbort, onCancelQueued, onRetry, onViewAll }) {
  const [filter, setFilter] = useState("all");

  // Newest first: running, then queued, then finished history.
  const all = [
    ...(job ? [{ ...job, status: "running" }] : []),
    ...queue.map((j) => ({ ...j, status: "queued" })),
    ...history,
  ];

  const matches = (j) =>
    filter === "all" ? true
      : filter === "running" ? (j.status === "running" || j.status === "queued")
      : j.status === filter;

  const countOf = (f) =>
    f === "all" ? all.length : all.filter((j) => (
      f === "running" ? (j.status === "running" || j.status === "queued") : j.status === f
    )).length;

  const rows = all.filter(matches).slice(0, SHOWN);

  return (
    <section className="panel jobs-panel">
      <div className="jobs-head">
        <span className="panel-title">JOBS</span>
        <button className="btn btn-mini jobs-all" onClick={onViewAll}>VIEW ALL ▸</button>
      </div>

      <div className="jobs-filters">
        {FILTERS.map(([f, label]) => {
          const n = countOf(f);
          return (
            <button
              key={f}
              className={"fchip fchip-sm" + (filter === f ? " active" : "")}
              disabled={n === 0 && f !== "all"}
              onClick={() => setFilter(f)}
            >
              {label} <span className="fcount">{n}</span>
            </button>
          );
        })}
      </div>

      <div className="jobs-list">
      {!rows.length && (
        <div className="empty">
          {all.length ? "No jobs match this filter." : "No jobs yet — launch a render below."}
        </div>
      )}

      {rows.map((j) => {
        const [cls, label] = STATUS_CHIP[j.status] || ["chip-missing", j.status.toUpperCase()];
        const running = j.status === "running";
        const doneAgents = running
          ? AGENTS.filter((a) => (j.agents || {})[a.key] === "done").length
          : 0;
        const pct = running ? Math.round((doneAgents / AGENTS.length) * 100) : 0;
        const fails = failedKeys(j);
        const okCount = Object.values(j.results || {}).filter((r) => r.status === "ok").length;

        return (
          <div className={"job-card " + j.status} key={j.id}>
            <div className="job-card-head">
              <Chip cls={cls}>{label}</Chip>
              <span className="job-name">{running ? j.current_key || j.label : j.label}</span>
              <span className="job-elapsed">
                {running
                  ? fmtElapsed(j.started_at)
                  : j.status === "queued"
                    ? "waiting"
                    : fmtElapsed(j.started_at, j.finished_at)}
              </span>
              {j.status === "queued" && (
                <button className="btn btn-mini" title="Remove from queue"
                        onClick={() => onCancelQueued(j.id)}>✕</button>
              )}
            </div>

            {running && (
              <>
                <div className="job-bar"><div style={{ width: pct + "%" }} /></div>
                <div className="job-card-foot">
                  <span className="job-stat">{doneAgents}/{AGENTS.length} agents complete</span>
                  <button className="btn btn-mini btn-danger" onClick={onAbort}>✕ ABORT</button>
                </div>
              </>
            )}

            {!running && j.status !== "queued" && (
              <div className="job-card-foot">
                <span className="job-stat">
                  {(j.finished_at || "").replace("T", " ")}
                  {okCount > 0 && ` · ${okCount} ok`}
                  {fails.length > 0 && ` · ${fails.length} failed: ${fails.join(", ")}`}
                </span>
                {fails.length > 0 && (
                  <button className="btn btn-mini btn-primary" onClick={() => onRetry(fails)}>
                    ⟳ RETRY
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </section>
  );
}
