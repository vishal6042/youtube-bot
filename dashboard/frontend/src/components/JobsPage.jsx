import { useMemo, useState } from "react";
import { STEPS } from "../api.js";
import {
  Banner, Btn, Empty, PageHeader, Pager, Search, Seg, Select, Stat, StatusChip,
  fmtDuration, fmtWhen, usePaged,
} from "../ui.jsx";
import LiveRun from "./LiveRun.jsx";
import { cleanLog, explain, failedKeys, keysOf, secsBetween, stepSecs, stepsOf } from "../screens/jobUtil.js";
import "../screens/produce.css";

const RANGES = [
  { value: "any", label: "Any date" },
  { value: "today", label: "Today" },
  { value: "week", label: "Last 7 days" },
];

const whenOf = (j) => j.finished_at || j.started_at || j.created_at;
const isLive = (j) => j.status === "running" || j.status === "queued";
const matchesStatus = (j, f) => f === "all" || (f === "running" ? isLive(j) : j.status === f);

function inRange(j, range) {
  if (range === "any") return true;
  const t = new Date(whenOf(j) || "").getTime();
  if (isNaN(t)) return false;
  const midnight = new Date().setHours(0, 0, 0, 0);
  return t >= (range === "today" ? midnight : midnight - 6 * 86400000);
}

/* The six steps of one topic within a job. A step left "active" in a job that
   is no longer running is where it stopped: the failure point of a failed job,
   or simply the interruption of a cancelled one. */
function stepRow(job, steps, topic) {
  const mine = steps.filter((s) => topic == null || s.topic === topic);
  const sawFailure = mine.some((s) => s.state === "failed");
  return STEPS.map((def) => {
    const rec = [...mine].reverse().find((s) => s.agent === def.key);
    let state = rec?.state || "none";
    if (state === "active" && job.status !== "running") {
      state = job.status === "failed" && !sawFailure ? "failed" : "stopped";
    }
    return { ...def, state, secs: rec?.secs ?? null };
  });
}

function pipsLabel(job, row) {
  if (job.status === "queued") return "Not started";
  const done = row.filter((s) => s.state === "done").length;
  const bad = row.findIndex((s) => s.state === "failed");
  if (bad >= 0) return `Failed at step ${bad + 1} of ${row.length}`;
  if (job.status === "cancelled") return `Cancelled after ${done} of ${row.length} steps`;
  return `${done} of ${row.length} steps done`;
}

function Pips({ job, row }) {
  return (
    <div className="steps" role="img" aria-label={pipsLabel(job, row)}>
      {row.map((s) => (
        <i key={s.key} className={s.state === "done" ? "" : s.state === "failed" ? "x"
          : s.state === "active" ? "a" : "o"} />
      ))}
    </div>
  );
}

function VideoCell({ job, titles }) {
  const keys = keysOf(job);
  if (keys.length === 1) {
    const title = titles?.[keys[0]];
    return title
      ? <><div className="t">{title}</div><div className="k">{keys[0]}</div></>
      : <div className="t num">{keys[0]}</div>;
  }
  return (
    <>
      <div className="t">{job.label}</div>
      {keys.length > 0 && <div className="k">{keys.join(", ")}</div>}
    </>
  );
}

const STATE_WORD = {
  done: ["Done", "var(--go)"], failed: ["Failed", "var(--bad)"], active: ["Running", "var(--info)"],
  stopped: ["Stopped here", "var(--warn)"],
};

function StepTimeline({ job, steps, topic }) {
  const row = stepRow(job, steps, topic);
  return (
    <div className="step-grid tight">
      {row.map((s) => {
        const [word, color] = STATE_WORD[s.state] || [job.status === "running" ? "Waiting" : "Not reached", null];
        return (
          <div key={s.key} className={"card step-card" + (s.state === "failed" ? " bad" : "")}
               style={{ padding: "12px 14px" }}>
            <b className={color ? undefined : "muted"}>{s.label}</b>
            <div className={color ? "sub" : "sub faint"} style={color ? { color } : undefined}>
              {word}
              {s.secs != null && s.state !== "active" && (
                <span className="num muted"> · {stepSecs(s.secs)}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Detail({ job, history, titles }) {
  const steps = stepsOf(job);
  const topics = [...new Set(steps.map((s) => s.topic).filter(Boolean))];
  const groups = topics.length ? topics : [null];
  const results = Object.entries(job.results || {});
  const fails = results.filter(([, r]) => r.status === "failed");
  const saved = results.filter(([, r]) => r.status === "ok" && r.export);
  const log = cleanLog(job.log);
  // History is newest first, so anything before this job ran after it.
  const at = history.findIndex((h) => h.id === job.id);
  const fixedSince = (key) =>
    at > 0 && history.slice(0, at).some((h) => h.results?.[key]?.status === "ok");

  return (
    <div className="split">
      <div className="wide stack">
        {!steps.length && (
          <div className="muted" style={{ fontSize: 13 }}>No step detail was recorded for this job.</div>
        )}
        {steps.length > 0 && groups.map((topic) => (
          <div key={topic || "all"}>
            {groups.length > 1 && (
              <div style={{ marginBottom: 6 }}>
                {titles?.[topic] && <span style={{ fontWeight: 550 }}>{titles[topic]} </span>}
                <span className="num faint" style={{ fontSize: 12 }}>{topic}</span>
              </div>
            )}
            <StepTimeline job={job} steps={steps} topic={topic} />
          </div>
        ))}
      </div>

      <div className="rail" style={{ gap: 12 }}>
        {fails.map(([key, r]) => {
          const failedStep = stepRow(job, steps, topics.includes(key) ? key : null)
            .find((s) => s.state === "failed");
          return (
            <div key={key} className="banner" style={{ "--c": "#ff6b6b" }}>
              <div style={{ minWidth: 0 }}>
                <b>{explain(r.error)}</b>
                <div className="muted" style={{ fontSize: 13 }}>
                  {fails.length > 1 && <span className="num">{key} · </span>}
                  {failedStep ? `Stopped at the ${failedStep.label.toLowerCase()} step. ` : ""}
                  {fixedSince(key) ? "Fixed since: a later run of this video completed." : ""}
                </div>
                {r.error && (
                  <details className="more sm">
                    <summary>Show details</summary>
                    <code className="num" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{r.error}</code>
                  </details>
                )}
              </div>
            </div>
          );
        })}
        {job.status === "failed" && !fails.length && (
          <div className="banner" style={{ "--c": "#ff6b6b" }}>
            <div>
              <b>{explain("")}</b>
              <div className="muted" style={{ fontSize: 13 }}>The log below is the only record.</div>
            </div>
          </div>
        )}
        {saved.map(([key, r]) => (
          <div key={key} className="muted" style={{ fontSize: 13 }}>
            Saved to <span className="num" style={{ overflowWrap: "anywhere" }}>{r.export}</span>
          </div>
        ))}
        {log.length > 0 && (
          <details className="more sm">
            <summary>Show the log ({log.length} lines)</summary>
            <pre className="num logbox" tabIndex={0} aria-label="Job log">{log.join("\n")}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

function JobRow({ job, open, onToggle, history, titles, onRetry, onCancel, onCancelQueued }) {
  const steps = useMemo(() => stepsOf(job), [job]);
  const topics = [...new Set(steps.map((s) => s.topic).filter(Boolean))];
  const row = stepRow(job, steps, topics.length ? topics[topics.length - 1] : null);
  const expandable = job.status !== "queued";
  const fails = failedKeys(job);
  const retry = fails.length ? fails : (job.status === "failed" || job.status === "cancelled") ? job.keys || [] : [];
  const name = keysOf(job)[0] || job.label;
  const took = job.status === "running" ? secsBetween(job.started_at)
    : job.started_at && job.finished_at ? secsBetween(job.started_at, job.finished_at) : null;
  const stopped = job.status === "failed" || job.status === "cancelled";

  return (
    <>
      <tr className={open ? "open" : undefined}>
        <td>
          {expandable && (
            <Btn kind="ghost" size="sm" icon={open ? "down" : "right"}
                 iconOnly={`${open ? "Hide" : "Show"} steps for ${name}`}
                 aria-expanded={open} onClick={onToggle} />
          )}
        </td>
        <td><VideoCell job={job} titles={titles} /></td>
        <td>
          <StatusChip state={job.status} />
          {job.status === "done" && fails.length > 0 && (
            <div style={{ color: "var(--bad)", fontSize: 12.5, marginTop: 4 }}>{fails.length} failed</div>
          )}
        </td>
        <td className="muted">
          {job.status === "queued" ? "Waiting"
            : job.status === "running" ? `Started ${fmtWhen(job.started_at)}`
            : fmtWhen(job.finished_at)}
        </td>
        <td className={"r num" + (took == null ? " faint" : "")}>
          {took != null ? fmtDuration(took) : stopped ? "stopped" : ""}
        </td>
        <td><Pips job={job} row={row} /></td>
        <td className="r">
          {job.status === "running" && onCancel && (
            <Btn kind="danger" size="sm" onClick={onCancel}>Abort</Btn>
          )}
          {job.status === "queued" && onCancelQueued && (
            <Btn kind="ghost" size="sm" icon="close" iconOnly={`Remove ${name} from the queue`}
                 onClick={() => onCancelQueued(job.id)} />
          )}
          {!isLive(job) && retry.length > 0 && (
            <Btn size="sm" onClick={() => onRetry(retry)}
                 aria-label={`${job.status === "cancelled" ? "Run again" : "Retry"}: ${retry.join(", ")}`}>
              {job.status === "cancelled" ? "Run again" : "Retry"}
            </Btn>
          )}
        </td>
      </tr>
      {open && (
        <tr className="open detail">
          <td />
          <td colSpan={6}><Detail job={job} history={history} titles={titles} /></td>
        </tr>
      )}
    </>
  );
}

/* `titles` is an optional { topicKey: title } map; jobs themselves only carry
   topic keys, so without it the key is the primary text. */
export default function JobsPage({ job, queue = [], history = [], failures = [], lines, onRetry,
                                   onCancel, onCancelQueued, onNewRender, titles }) {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [range, setRange] = useState("any");
  const [open, setOpen] = useState(() => new Set());

  // Newest first: running, then queued, then finished.
  const all = useMemo(() => [
    ...(job ? [{ ...job, status: "running" }] : []),
    ...queue.map((j) => ({ ...j, status: "queued" })),
    ...history,
  ], [job, queue, history]);

  const needle = q.trim().toLowerCase();
  const searched = all.filter((j) => inRange(j, range) && (!needle
    || [j.label, ...keysOf(j), ...keysOf(j).map((k) => titles?.[k])]
      .some((s) => s && String(s).toLowerCase().includes(needle))));
  const rows = searched.filter((j) => matchesStatus(j, filter));
  const countOf = (f) => searched.filter((j) => matchesStatus(j, f)).length;
  const paged = usePaged(rows, 10, `${filter}|${needle}|${range}`);

  const done = history.filter((j) => j.status === "done");
  const failed = history.filter((j) => j.status === "failed");
  // Median wall-clock per video across completed jobs, like the server's plan estimate.
  const samples = done
    .map((j) => {
      const s = j.started_at && j.finished_at ? secsBetween(j.started_at, j.finished_at) : null;
      return s ? s / Math.max(1, Object.keys(j.results || {}).length) : null;
    })
    .filter(Boolean)
    .sort((a, b) => a - b);
  const typical = samples.length ? samples[Math.floor(samples.length / 2)] : null;

  const toggle = (id) => setOpen((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <>
      <PageHeader title="Jobs" sub="Every render, newest first. Open a row to see each step.">
        {onNewRender && <Btn kind="primary" icon="play" onClick={onNewRender}>New render</Btn>}
      </PageHeader>

      {failures.length > 0 && (
        <Banner tone="bad" role="alert"
                title={`${failures.length} video${failures.length === 1 ? "" : "s"} failed on the last run`}
                actions={failures.length > 1 && (
                  <Btn size="sm" icon="refresh" onClick={() => onRetry(failures.map((f) => f.key))}>
                    Retry all
                  </Btn>
                )}>
          <ul className="plain-list stack" style={{ gap: 6, marginTop: 6 }}>
            {failures.map((f) => (
              <li key={f.key} className="rowf" style={{ paddingTop: 0, border: 0 }}>
                <span style={{ flex: "1 1 220px", minWidth: 0 }}>
                  {titles?.[f.key] && <span style={{ color: "var(--text)" }}>{titles[f.key]} </span>}
                  <span className="num">{f.key}</span>
                  {" · "}{explain(f.error)}
                  {f.at && <span className="faint"> · {fmtWhen(f.at)}</span>}
                </span>
                <Btn size="sm" onClick={() => onRetry([f.key])} aria-label={`Retry ${f.key}`}>Retry</Btn>
              </li>
            ))}
          </ul>
        </Banner>
      )}

      <LiveRun job={job} queue={queue} lines={lines} titles={titles}
               onCancel={onCancel} onCancelQueued={onCancelQueued} />

      <section className="cols c4" aria-label="Job totals">
        <Stat label="Running now" value={job ? 1 : 0}
              note={queue.length ? `${queue.length} queued` : job ? "nothing queued behind it" : "pipeline idle"} />
        <Stat label="Completed" value={done.length}
              note={history.length ? `of the last ${history.length}` : undefined} />
        <Stat label="Failed" value={failed.length} tone={failed.length ? "bad" : undefined}
              note={failed.length ? `last on ${fmtWhen(whenOf(failed[0]), { time: false })}`
                : history.length ? `none in the last ${history.length}` : undefined} />
        {typical != null && (
          <Stat label="Typical time" value={typical < 90 ? fmtDuration(typical) : `~${Math.round(typical / 60)} min`}
                note="per video" />
        )}
      </section>

      <div className="rowf">
        <Seg label="Status" value={filter} onChange={setFilter} options={[
          { value: "all", label: "All", count: countOf("all") },
          { value: "running", label: "Running", count: countOf("running") },
          { value: "done", label: "Completed", count: countOf("done") },
          { value: "failed", label: "Failed", count: countOf("failed") },
          { value: "cancelled", label: "Cancelled", count: countOf("cancelled") },
        ]} />
        <span className="spacer" />
        <Search value={q} onChange={setQ} placeholder="Search by video" label="Search jobs" />
        <Select value={range} onChange={setRange} options={RANGES} label="Date range" />
      </div>

      <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Job list">
        {!rows.length ? (
          all.length ? (
            <Empty icon="search" title="No jobs match">Try a different status, date or search.</Empty>
          ) : (
            <Empty icon="jobs" title="No jobs yet"
                   action={onNewRender && <Btn size="sm" icon="play" onClick={onNewRender}>New render</Btn>}>
              Renders you start show up here with every step they went through.
            </Empty>
          )
        ) : (
          <>
            <div className="scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 44 }}><span className="sr">Show steps</span></th>
                    <th>Video</th><th>Result</th><th>Finished</th><th className="r">Took</th><th>Steps</th>
                    <th style={{ width: 110 }}><span className="sr">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {paged.slice.map((j) => (
                    <JobRow key={j.id} job={j} open={open.has(j.id)} onToggle={() => toggle(j.id)}
                            history={history} titles={titles} onRetry={onRetry}
                            onCancel={onCancel} onCancelQueued={onCancelQueued} />
                  ))}
                </tbody>
              </table>
            </div>
            <Pager p={paged} noun="jobs" sizes={[10, 25]} style={{ padding: "14px 12px 0" }} />
          </>
        )}
      </section>
    </>
  );
}
