import { Bar, Btn, Chip, Icon, Thumb, fmtNum } from "../../ui.jsx";
import { mb, stageLabel } from "./Transmission.jsx";
import "../../screens/publish.css";

/* The server's check names, in the words the rest of the app uses. */
const CHECK_NAMES = {
  "YouTube authorisation": "Signed in to YouTube",
  "Upload channel": "Right channel",
  "Export files": "Video files",
  "Daily quota": "Daily limit",
};

function BatchRow({ b, onRemove }) {
  return (
    <li className="b-row">
      <Thumb item={b} small />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="t">{b.title}</div>
        {b.state === "queued" && <div className="s">{mb(b.bytes) || "Waiting to send"}</div>}
        {b.state === "running" && <div className="s num">{stageLabel(b.stage)} {b.pct ?? 0}%</div>}
        {b.state === "done" && (
          <div className="s">
            {b.url
              ? <a className="link" href={b.url} target="_blank" rel="noopener noreferrer">Private on YouTube</a>
              : "Uploaded as Private"}
          </div>
        )}
        {b.state === "failed" && <div className="s bad">Failed: {b.error || "no reason given"}</div>}
      </div>
      {b.state !== "running" && (
        <Btn kind="ghost" size="sm" icon="close" iconOnly={`Remove ${b.title} from the batch`}
             onClick={() => onRemove(b)} />
      )}
    </li>
  );
}

export function BatchCard({ rows, pending, run, pre, busy, onSend, onRemove, onClear }) {
  const n = pending.length;
  const blockedByChecks = n > 0 && !run.running && pre !== undefined && !pre?.ok;
  return (
    <section className="card" style={n ? { borderColor: "rgba(200,245,96,.4)" } : undefined}>
      <div className="card-head">
        <h2>Today's batch</h2>
        <Chip plain tone={rows.length ? "go" : "idle"} className="num">{rows.length}</Chip>
        <span className="spacer" />
        {rows.some((b) => b.state === "done") && (
          <Btn kind="ghost" size="sm" onClick={onClear}>Clear finished</Btn>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>
          Nothing in the batch yet. Use Add to batch on a video in the queue.
        </p>
      ) : (
        <ul className="b-list">
          {rows.map((b) => <BatchRow key={b.key} b={b} onRemove={onRemove} />)}
        </ul>
      )}

      <Btn kind="primary" icon="upload" style={{ width: "100%", marginTop: 14 }}
           disabled={busy || run.running || !n || !pre?.ok} onClick={onSend}>
        {run.running
          ? `Uploading: ${stageLabel(run.stage)} ${run.pct ?? 0}%`
          : n ? `Send ${n} video${n === 1 ? "" : "s"} to YouTube` : "Nothing to send"}
      </Btn>
      {blockedByChecks && (
        <p className="q-note" style={{ marginTop: 10, color: "var(--warn)" }}>
          The checks below have to pass before anything can be sent.
        </p>
      )}
      <p className="faint q-note" style={{ marginTop: 10 }}>
        Uploads arrive as Private. Switch them to Public in YouTube Studio.
      </p>
    </section>
  );
}

/* One row across the page: the checks are a status line, not a destination. */
export function ChecksCard({ pre, onRecheck }) {
  const checks = pre?.checks || [];
  const failed = checks.filter((c) => !c.ok).length;
  return (
    <section className="card chk-strip" aria-label="Checks before sending">
      <div className="rowf" style={{ flexWrap: "nowrap", flex: "none" }}>
        <h2>Checks</h2>
        {pre === undefined ? <Chip plain tone="idle">Checking</Chip>
          : pre === null ? <Chip plain tone="bad">Could not check</Chip>
          : failed ? <Chip plain tone="bad">{failed} failed</Chip>
          : <Chip plain tone="go">All passed</Chip>}
      </div>
      {pre === undefined && !checks.length && (
        <div className="skel" style={{ height: 16, flex: "1 1 200px" }} aria-busy="true" aria-label="Checking" />
      )}
      {pre === null && (
        <span className="muted" style={{ fontSize: 13, flex: "1 1 240px" }}>
          The checks did not come back. Make sure the dashboard server is running, then re-check.
        </span>
      )}
      {checks.length > 0 && (
        <ul className="chk-list">
          {checks.map((c) => (
            <li key={c.name}>
              <span className={"dot" + (c.ok ? "" : " off")} />
              <span>
                {CHECK_NAMES[c.name] || c.name}
                <span className="sr">{c.ok ? " passed" : " failed"}</span>
              </span>
              <span className="d" style={c.ok ? undefined : { color: "var(--bad)" }}>{c.detail}</span>
            </li>
          ))}
        </ul>
      )}
      <Btn kind="ghost" size="sm" icon="refresh" disabled={pre === undefined} onClick={onRecheck}
           style={{ marginLeft: "auto", flex: "none" }}>
        Re-check
      </Btn>
    </section>
  );
}

export function LimitCard({ quota }) {
  const total = quota.slots_total || 5;
  const used = quota.uploads_today || 0;
  const full = quota.slots_left === 0;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Today's limit</h2>
        <span className="spacer" />
        <span className="num" style={full ? { color: "var(--warn)" } : undefined}>{used} of {total} used</span>
      </div>
      <div className="rowf" style={{ gap: 6, flexWrap: "nowrap" }} role="img"
           aria-label={`${used} of ${total} upload slots used`}>
        {Array.from({ length: total }, (_, i) => (
          <Bar key={i} pct={i < used ? 100 : 0} color={full ? "var(--warn)" : undefined} style={{ flex: 1 }} />
        ))}
      </div>
      <p className="faint q-note" style={{ marginTop: 10 }}
         title={quota.daily_units != null
           ? `${fmtNum(quota.units_used)} of ${fmtNum(quota.daily_units)} quota units used${
             quota.per_upload ? `, ${fmtNum(quota.per_upload)} per upload` : ""}`
           : undefined}>
        {full ? "No uploads left today. " : `${quota.slots_left} left today. `}
        Resets at midnight Pacific time.
      </p>
    </section>
  );
}
