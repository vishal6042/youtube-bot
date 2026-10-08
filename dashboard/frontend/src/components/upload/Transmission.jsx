import { Banner, Bar, Btn, Chip, Icon } from "../../ui.jsx";
import "../../screens/publish.css";

/* The five stages the uploader reports, in order. Uploads run strictly one at
   a time, so one row of steps describes the whole run. */
export const STAGES = [
  { id: "authorising", label: "Sign-in", hint: "Checking the sign-in and the channel" },
  { id: "uploading", label: "Transfer", hint: "Sending the video file" },
  { id: "thumbnail", label: "Thumbnail", hint: "Setting the thumbnail" },
  { id: "playlist", label: "Playlist", hint: "Adding it to its playlist" },
  { id: "recording", label: "Record", hint: "Marking it as uploaded" },
];
const ORDER = ["starting", ...STAGES.map((s) => s.id), "done"];

export const mb = (bytes) => (bytes ? `${(bytes / 1e6).toFixed(1)} MB` : "");
export const stageLabel = (id) => STAGES.find((s) => s.id === id)?.label || "Starting";

const plural = (n) => `${n} video${n === 1 ? "" : "s"}`;

function Steps({ idx }) {
  return (
    <div className="tx-steps" role="list" aria-label="Upload steps">
      {STAGES.map((s) => {
        const at = ORDER.indexOf(s.id);
        const state = at < idx ? "done" : at === idx ? "running" : "waiting";
        return (
          <Chip key={s.id} plain tone={state === "waiting" ? "idle" : "go"} role="listitem"
                aria-label={`${s.label}: ${state}`} style={state === "waiting" ? { opacity: .7 } : undefined}>
            {state === "done" && <Icon name="check" />}
            {state === "running" && <span className="spin" />}
            {s.label}
          </Chip>
        );
      })}
    </div>
  );
}

/* Live card for a run in flight, and its result once it ends. Stays up after
   the last upload because the result (and the Private reminder) is the part
   worth reading; clearing the finished batch dismisses it. */
export default function Transmission({ rows, run }) {
  const active = rows.filter((b) => b.state === "queued" || b.state === "running");
  const done = rows.filter((b) => b.state === "done");
  const failed = rows.filter((b) => b.state === "failed");
  const finished = !run.running && active.length === 0 && rows.length > 0;
  if (!run.running && !finished) return null;

  const warnings = rows.flatMap((b) => (b.warnings || []).map((w) => `${b.title}: ${w}`));

  if (run.running) {
    const current = rows.find((b) => b.key === run.current) || active[0];
    const stage = STAGES.find((s) => s.id === run.stage);
    const pct = Math.round(run.pct ?? 0);
    const idx = Math.max(0, ORDER.indexOf(run.stage || "starting"));
    const moving = run.stage === "uploading";
    const pos = rows.findIndex((b) => b.key === current?.key) + 1;
    return (
      <section className="card" aria-label="Upload in progress" style={{ borderColor: "rgba(200,245,96,.4)" }}>
        <div className="rowf" style={{ flexWrap: "nowrap", gap: 14 }}>
          <span className="dot live" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="muted" style={{ fontSize: 13 }}>
              Sending to YouTube{pos > 0 ? ` · video ${pos} of ${rows.length}` : ""}
            </div>
            <h2 style={{ fontSize: 22, letterSpacing: "-.02em" }}>{current?.title || run.current || "Starting"}</h2>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="num" style={{ fontSize: 26, fontWeight: 500 }}>{pct}%</div>
            <div className="muted num" style={{ fontSize: 12.5 }}>
              {current?.bytes ? `${mb((current.bytes * pct) / 100) || "0.0 MB"} of ${mb(current.bytes)}` : stage?.hint || "Getting ready"}
            </div>
          </div>
        </div>

        {/* The video travels from this computer to the channel: the track fills
            with the bytes sent and each gate lights as the upload passes it. */}
        <div className="up-flow">
          <div className="up-end">
            <div className="up-box"><Icon name="screen" /></div>
            <b>This computer</b>
            <span className="muted" style={{ fontSize: 12.5 }}>{mb(current?.bytes) || "video file"}</span>
          </div>
          <div className="up-lane">
            <div className="up-track" role="progressbar" aria-label="Upload progress"
                 aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: pct + "%" }} />
            </div>
            {moving && <><span className="up-pkt" /><span className="up-pkt" /><span className="up-pkt" /><span className="up-pkt" /></>}
            <ol className="up-gates" aria-label="Upload steps">
              {STAGES.map((s) => {
                const at = ORDER.indexOf(s.id);
                const state = at < idx ? "done" : at === idx ? "run" : "wait";
                return (
                  <li key={s.id} className={"up-gate " + state}
                      aria-label={`${s.label}: ${state === "done" ? "done" : state === "run" ? "running" : "waiting"}`}>
                    <div className="up-pin">{state === "done" && <Icon name="check" />}</div>
                    <span>{s.label}</span>
                  </li>
                );
              })}
            </ol>
          </div>
          <div className="up-end">
            <div className={"up-box dest" + (moving ? " ping" : "")}><Icon name="youtube" /></div>
            <b>YouTube</b>
            <span className="muted" style={{ fontSize: 12.5 }}>{stage?.hint || "Getting ready"}</span>
          </div>
        </div>

        <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>Today's batch</div>
        <div className="rowf" style={{ alignItems: "stretch" }}>
          {rows.map((b) => {
            const live = b.key === current?.key;
            return (
              <div key={b.key} className={"up-item" + (live ? " run" : "")}>
                <span className={"dot " + (live ? "live" : b.state === "done" ? "" : b.state === "failed" ? "off" : "idle")} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  {live ? <b>{b.title}</b> : <span>{b.title}</span>}
                  {live
                    ? <Bar pct={pct} running height={5} style={{ marginTop: 8 }} />
                    : <div className="faint" style={{ fontSize: 12.5 }}>
                        {b.state === "done" ? "Uploaded" : b.state === "failed" ? "Failed" : "Waiting"}
                      </div>}
                </div>
                {live && <span className="num muted" style={{ fontSize: 12.5 }}>{pct}%</span>}
              </div>
            );
          })}
        </div>
        <p className="faint q-note" style={{ marginTop: 12 }}>
          If one upload fails the run stops there, so no further daily limit is spent. Finished uploads arrive as Private.
        </p>
        {warnings.length > 0 && <p className="faint q-note" style={{ marginTop: 6 }}>{warnings.join(" · ")}</p>}
      </section>
    );
  }

  return (
    <section className="card" aria-label="Upload result">
      <div className="card-head">
        <h2>{failed.length ? "Upload stopped" : "Upload finished"}</h2>
        <Chip tone={failed.length ? "bad" : "go"} plain>
          {done.length} uploaded{failed.length ? `, ${failed.length} failed` : ""}
        </Chip>
      </div>
      {!failed.length && (
        <>
          <Steps idx={ORDER.length - 1} />
          <Bar pct={100} />
        </>
      )}
      {warnings.length > 0 && <p className="muted q-note" style={{ marginTop: 10 }}>{warnings.join(" · ")}</p>}
      {done.length > 0 && (
        <p className="faint q-note" style={{ marginTop: 10 }}>
          {done.length === 1 ? "It is" : `All ${plural(done.length)} are`} Private on YouTube.
          Switch {done.length === 1 ? "it" : "them"} to Public in YouTube Studio, then clear the
          finished uploads from today's batch.
        </p>
      )}
    </section>
  );
}

/* A stopped run, in plain language. The uploader's own error text is often a
   raw API exception, so it only ever appears inside the details. */
export function StoppedBanner({ reason, rows, titleOf, onDismiss }) {
  const m = /^([\w.-]+): /.exec(reason);
  const failed = (m && rows.find((b) => b.key === m[1])) || rows.find((b) => b.state === "failed");
  const name = failed?.title || (m ? titleOf(m[1]) : null);
  const body = name
    ? "That upload failed, so nothing else was sent and no further quota was spent."
    : /quota/i.test(reason)
      ? "Today's upload limit is used up. Try again after it resets at midnight Pacific time."
      : "Nothing further was sent.";
  return (
    <Banner tone="bad" role="alert"
            title={name ? `The last run stopped at ${name}` : "The last run stopped early"}
            actions={<Btn size="sm" onClick={onDismiss}>Dismiss</Btn>}>
      {body}
      <details className="raw-details">
        <summary>Show details</summary>
        <pre>{reason}</pre>
      </details>
    </Banner>
  );
}
