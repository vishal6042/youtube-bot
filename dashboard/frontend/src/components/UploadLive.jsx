import TransmissionArc, { mb } from "./TransmissionArc.jsx";

/* The upload panel on the Mission page.
 *
 * Visible whenever the batch has anything in it — staged, running, or finished.
 * It deliberately does NOT vanish the moment a run completes: the result is the
 * part worth reading (the links, and the reminder that the videos are Private),
 * and it disappearing on the last frame of the animation is worse than useless.
 * Dismiss it with CLEAR, which is also what empties the finished batch.
 *
 * With an empty batch it renders nothing at all, so Mission stays a renders-only
 * dashboard when there is no upload work.
 */
export default function UploadLive({ batch = [], run = {}, onOpen, onClear }) {
  if (!run.running && batch.length === 0) return null;

  const pending = batch.filter((b) => b.state === "queued" || b.state === "running");
  const done = batch.filter((b) => b.state === "done");
  const failed = batch.filter((b) => b.state === "failed");
  const current = batch.find((b) => b.key === run.current) || pending[0] || done.at(-1);
  const finished = !run.running && pending.length === 0 && batch.length > 0;

  const headline = run.running
    ? `${current?.title || run.current} — ${run.stage}`
    : finished
      ? `${done.length} uploaded${failed.length ? `, ${failed.length} failed` : ""}`
      : `${pending.length} staged, not started`;

  return (
    <section className="panel">
      <div className="jobs-head">
        <span className="panel-title">
          {run.running ? "UPLOAD IN FLIGHT" : finished ? "UPLOAD COMPLETE" : "UPLOAD STAGED"}
        </span>
        <span className="ul-meta">
          {headline}
          {finished && onClear && (
            <button className="btn btn-mini" onClick={onClear}>CLEAR</button>
          )}
          <button className="btn btn-mini ul-open" onClick={onOpen}>UPLOAD CONTROL ▸</button>
        </span>
      </div>

      <TransmissionArc item={current} run={run} />

      <div className="ul-rows">
        {batch.map((b) => (
          <div className={"ul-row " + b.state} key={b.key}>
            <span className="ul-dot" />
            <span className="ul-title">{b.title || b.key}</span>
            <span className="ul-size">{mb(b.bytes)}</span>
            <span className="ul-state">
              {b.state === "running" ? `${b.stage} ${b.pct}%`
                : b.state === "done" ? (
                    <a href={b.url} target="_blank" rel="noreferrer" className="uc-link">
                      ✅ private on YouTube ↗
                    </a>
                  )
                : b.state === "failed" ? `✕ ${b.error}`
                : "queued"}
            </span>
          </div>
        ))}
      </div>

      {batch.some((b) => (b.warnings || []).length > 0) && (
        <div className="lc-note">
          {batch.flatMap((b) => (b.warnings || []).map((w) => `${b.title || b.key}: ${w}`)).join(" · ")}
        </div>
      )}

      {run.stopped_reason && (
        <div className="lc-note lc-note-warn">⚠ Run stopped: {run.stopped_reason}</div>
      )}

      {finished && done.length > 0 && (
        <div className="lc-note">
          {done.length === 1 ? "It is" : "They are"} <b>Private</b> — flip{" "}
          {done.length === 1 ? "it" : "them"} to Public in YouTube Studio. This panel clears
          when you press CLEAR.
        </div>
      )}
    </section>
  );
}
