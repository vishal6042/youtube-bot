import { useEffect, useMemo, useRef } from "react";
import { STEPS } from "../api.js";
import { Bar, Btn, Chip, Icon, MODE_LABEL } from "../ui.jsx";
import { cleanLog, keysOf, secsBetween, stepSecs } from "../screens/jobUtil.js";
import "../screens/produce.css";

/* One entry per pipeline step: done | active | failed | idle, plus a percent. */
function stepStates(job) {
  const prog = job?.progress || {};
  const allDone = job?.stage === "exported";
  return STEPS.map((s) => {
    const p = prog[s.key] || { state: job?.agents?.[s.key] || "idle", pct: 0 };
    const state = allDone ? "done" : p.state;
    const pct = state === "done" || state === "failed" ? 100 : state === "active" ? p.pct || 0 : 0;
    return { ...s, state, pct };
  });
}

/* Seconds left for the current video, or null when it cannot be told. The
   server's percent is elapsed / typical, so elapsed and percent give the
   typical length back. The video step dwarfs the rest, so nothing is claimed
   before it has started, nor once a step is pinned at the server's 95% cap. */
function secsLeft(job, steps) {
  const video = steps.find((s) => s.key === "video");
  if (!video || video.state === "idle" || video.state === "failed") return null;
  const active = steps.filter((s) => s.state === "active");
  if (!active.length) return null;
  let left = 0;
  for (const s of active) {
    const rec = [...(job.steps || [])].reverse()
      .find((r) => r.agent === s.key && r.state === "active" && r.at);
    const elapsed = rec ? secsBetween(rec.at) : null;
    if (elapsed == null || s.pct < 5 || s.pct >= 95) return null;
    left = Math.max(left, (elapsed * (100 - s.pct)) / s.pct);
  }
  return left;
}

function leftText(secs) {
  if (secs == null) return null;
  if (secs < 45) return "Less than a minute left for this video";
  const m = Math.max(1, Math.round(secs / 60));
  return `About ${m} minute${m === 1 ? "" : "s"} left for this video`;
}

function Name({ k, titles }) {
  const title = titles?.[k];
  return title
    ? <><span>{title}</span> <span className="num faint" style={{ fontSize: 12 }}>{k}</span></>
    : <span className="num">{k}</span>;
}

const clock = (secs) => {
  const t = Math.max(0, Math.round(secs));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

/* The chart type being drawn, read from the renderer's own log line
   ("Rendering bar_race -> ..."). Null until that line has been printed. */
function chartMode(lines) {
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = /Rendering (\w+) ->/.exec(lines[i]);
    if (m) return m[1];
  }
  return null;
}

const BARS = [
  ["#c8f560", 54, 86, 2.3], ["#7fd4ff", 70, 52, 1.9], ["#ffc857", 38, 58, 2.7],
  ["#a78bfa", 22, 34, 2.1], ["#ff7a90", 28, 20, 3.1], ["#3ddc97", 12, 24, 2.5],
];

/* A looping sketch of the chart type in a 9:16 frame. It stands in for the
   video being drawn: the pipeline cannot show real frames mid-render. */
function Stage({ title, mode, running }) {
  const lines = mode === "line_grow" || mode === "line_multi";
  return (
    <div className="st-wrap">
      <div className={"st-phone" + (running ? " run" : "")} aria-hidden="true">
        <div className="st-title">{title}</div>
        {lines ? (
          <svg className="st-lines" viewBox="0 0 180 200" preserveAspectRatio="none">
            <path d="M4 180 C40 170 60 150 90 120 S150 40 176 22" stroke="#c8f560" />
            {mode === "line_multi" && <path d="M4 150 C50 146 80 130 110 112 S160 80 176 70" stroke="#7fd4ff" />}
          </svg>
        ) : (
          BARS.map(([c, from, to, d]) => (
            <div key={c} className="st-row" style={{ "--c": c, "--a": from + "%", "--b": to + "%", "--d": d + "s" }}>
              <b />
            </div>
          ))
        )}
        <div className="st-mode">{MODE_LABEL[mode] || "Video"}</div>
      </div>
      <span className="faint" style={{ fontSize: 12 }}>Sketch of the chart type</span>
    </div>
  );
}

export function Dial({ pct, running, size }) {
  return (
    <div className={"st-dial" + (running ? " run" : "") + (size === "sm" ? " sm" : size === "md" ? " md" : "")}
         style={{ "--p": pct + "%" }} role="progressbar" aria-label="Overall progress"
         aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="st-dial-in">
        <div className="num st-pct">{pct}%</div>
        {size !== "sm" && <div className="muted" style={{ fontSize: 12 }}>overall</div>}
      </div>
    </div>
  );
}

function StepRow({ step, job }) {
  const { state } = step;
  const took = state === "done"
    ? [...(job.steps || [])].reverse()
        .find((r) => r.agent === step.key && r.state === "done"
          && (!job.current_key || r.topic === job.current_key))?.secs
    : null;
  const cls = state === "active" ? "run" : state === "done" ? "done" : state === "failed" ? "bad" : "wait";
  return (
    <li className={"st-step " + cls}>
      <span className="st-ico">
        {state === "done" && <Icon name="check" />}
        {state === "failed" && <Icon name="close" />}
      </span>
      <b style={{ flex: 1 }}>{step.label}</b>
      {state === "active" && step.key === "music" && (
        <span className="st-eq" aria-hidden="true"><i /><i /><i /><i /><i /></span>
      )}
      <span className="num st-note">
        {state === "active" && `${step.doing.toLowerCase()} · ${step.pct}%`}
        {state === "done" && (took != null ? `took ${stepSecs(took)}` : "done")}
        {state === "failed" && "stopped here"}
        {state === "idle" && step.hint}
      </span>
      <span className="sr">
        {state === "done" ? "done" : state === "active" ? "running" : state === "failed" ? "failed" : "waiting"}
      </span>
    </li>
  );
}

function Log({ lines }) {
  const ref = useRef(null);
  const text = useMemo(() => cleanLog(lines).join("\n"), [lines]);
  // Follow the tail only while the reader is already at the bottom.
  useEffect(() => {
    const el = ref.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 80) el.scrollTop = el.scrollHeight;
  }, [text]);
  return (
    <details className="more" style={{ marginTop: 14 }}>
      <summary>Show the full log</summary>
      <pre className="num logbox" ref={ref} tabIndex={0} aria-label="Render log">
        {text || "Nothing logged yet."}
      </pre>
    </details>
  );
}

/* The "while a render runs" card. `compact` is the Overview version. `titles`
   is an optional { topicKey: title } map; without it the key is shown. */
export default function LiveRun({ job, queue = [], lines = [], onCancel, onCancelQueued, compact, titles }) {
  if (!job && !queue.length) return null;

  const steps = stepStates(job);
  const overall = job ? Math.round(steps.reduce((n, s) => n + s.pct, 0) / steps.length) : 0;
  const active = steps.filter((s) => s.state === "active");
  const failed = steps.find((s) => s.state === "failed");
  const doing = !job ? "Waiting to start"
    : active.length > 1 ? `${active.map((s) => s.label).join(", ")} in progress`
    : active.length === 1 ? active[0].doing
    : job.stage === "exported" ? "Finishing up"
    : failed ? `${failed.label} step failed`
    : "Starting";
  const current = job ? job.current_key || keysOf(job)[0] : null;
  const waiting = queue.length ? `${queue.length} more queued` : "";
  const elapsed = job?.started_at ? secsBetween(job.started_at) : null;

  const head = (
    <div className="card-head" style={{ flexWrap: "wrap" }}>
      <span className={"dot " + (job ? "live" : "idle")} aria-hidden="true" />
      <h2>{job ? "Rendering now" : "Waiting to start"}</h2>
      <span className="muted" style={{ fontSize: 13, minWidth: 0 }}>
        {current ? <Name k={current} titles={titles} /> : job?.label}
        {waiting && (job ? " · " + waiting : `${queue.length} queued`)}
      </span>
      <span className="spacer" />
      {job && onCancel && <Btn kind="danger" size="sm" onClick={onCancel}>Abort</Btn>}
    </div>
  );

  if (compact) {
    return (
      <section className="card" aria-label="Render in progress">
        {head}
        {job && (
          <div className="rowf" style={{ flexWrap: "nowrap", gap: 18 }}>
            <Dial pct={overall} running size="sm" />
            <div style={{ flex: 1, minWidth: 0 }}>
            <Bar pct={overall} running height={8} />
            <div className="muted" style={{ fontSize: 13, margin: "8px 0 12px" }}>{doing}</div>
            <div className="rowf" style={{ gap: 6 }}>
              {steps.map((s) => (
                <Chip key={s.key} plain={s.state !== "active"}
                      tone={s.state === "failed" ? "bad" : s.state === "idle" ? "idle" : "go"}
                      style={s.state === "idle" ? { opacity: .7 } : undefined}
                      title={s.state === "active" ? `${s.pct}%` : undefined}>
                  {s.state === "done" && <Icon name="check" size={12} />}
                  {s.state === "failed" && <Icon name="close" size={12} />}
                  {s.label}
                  <span className="sr">
                    {s.state === "done" ? " done" : s.state === "active" ? " running"
                      : s.state === "failed" ? " failed" : " waiting"}
                  </span>
                </Chip>
              ))}
            </div>
            </div>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="card" aria-label="Render in progress">
      {head}
      {job && (
        <div className="st-studio">
          <Stage title={titles?.[current] || current || job.label} mode={chartMode(lines)}
                 running={steps.some((x) => x.key === "video" && x.state === "active")} />
          <div className="st-mid">
            <Dial pct={overall} running />
            <div style={{ textAlign: "center" }}>
              {elapsed != null && (
                <div className="num" style={{ fontSize: 20 }}>
                  {clock(elapsed)} <span className="muted" style={{ fontSize: 13, fontFamily: "var(--sans)" }}>elapsed</span>
                </div>
              )}
              <div className="muted" style={{ fontSize: 13 }}>{leftText(secsLeft(job, steps)) || doing}</div>
            </div>
          </div>
          <ol className="plain-list st-steps" aria-label="Steps">
            {steps.map((x) => <StepRow key={x.key} step={x} job={job} />)}
          </ol>
        </div>
      )}

      {queue.length > 0 && (
        <div style={{ marginTop: job ? 16 : 0 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>
            Up next ({queue.length})
          </div>
          <ol className="plain-list stack" style={{ gap: 6 }}>
            {queue.map((q, i) => {
              const keys = keysOf(q);
              return (
                <li key={q.id} className="rowf" style={{ flexWrap: "nowrap", paddingTop: i ? 6 : 0 }}>
                  <span className="num faint">{i + 1}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    {keys.length === 1 ? <Name k={keys[0]} titles={titles} /> : q.label}
                  </span>
                  <Chip tone="idle">Queued</Chip>
                  {onCancelQueued && (
                    <Btn kind="ghost" size="sm" icon="close"
                         iconOnly={`Remove ${keys[0] || q.label} from the queue`}
                         onClick={() => onCancelQueued(q.id)} />
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {job && <Log lines={lines} />}
    </section>
  );
}
