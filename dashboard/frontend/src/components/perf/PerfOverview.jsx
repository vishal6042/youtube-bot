import { Btn, Stat, fmtNum, fmtWhen } from "../../ui.jsx";
import { GrowthChart, N, StatusPill, TypeChip, signed } from "./perf.jsx";

const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const clock = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase();
};

function Tile({ label, children, warn }) {
  return (
    <div className="stack" style={{ gap: 8, padding: 16, borderRadius: 12,
      background: warn ? "color-mix(in srgb, var(--warn) 8%, var(--bg))" : "var(--bg)",
      border: `1px solid ${warn ? "color-mix(in srgb, var(--warn) 35%, transparent)" : "var(--line)"}` }}>
      <span style={{ fontSize: 12.5, color: warn ? "var(--warn)" : "var(--muted)" }}>{label}</span>
      {children}
    </div>
  );
}

const big = { fontFamily: "var(--mono)", fontSize: 30, fontWeight: 500, letterSpacing: "-.03em", lineHeight: 1.1 };

/* The top of the Overview: what happened today and how the channel is doing. */
export default function PerfOverview({ perf, error, quota, setView }) {
  if (error) {
    return <section className="card"><p className="muted">Channel stats are unavailable: {error}</p></section>;
  }
  if (!perf) return null;
  const { today, channel, growth, rising, latest } = perf.overview;
  const lf = perf.longform;
  const used = quota ? quota.uploads_today : null;
  const total = quota ? quota.slots_total : null;
  const markers = lf
    .filter((v) => v.posted_at && v.status === "live")
    .map((v) => {
      const words = v.title.replace(/[^\w\s'#-]/g, "").split(/\s+/);
      let label = "";
      for (const w of words) { if ((label + " " + w).trim().length > 18) break; label = (label + " " + w).trim(); }
      return { day: v.posted_at.slice(0, 10), label: label + (label.length < v.title.length ? "…" : "") };
    });
  const lfViews = lf.reduce((a, v) => a + (v.views || 0), 0);
  const lfLikes = lf.reduce((a, v) => a + (v.likes || 0), 0);
  const lfComments = lf.reduce((a, v) => a + (v.comments || 0), 0);
  const lfShorts = lf.reduce((a, v) => a + (v.shorts_views || 0), 0);

  return (
    <>
      <section className="card" aria-labelledby="today-h">
        <div className="card-head"><h2 id="today-h">Today</h2></div>
        <div className="cols c4" style={{ gap: 14 }}>
          <Tile label="Uploaded today">
            <span style={big}>{today.uploaded}</span>
            <span className="muted" style={{ fontSize: 13 }}>
              {today.uploaded
                ? [today.shorts && plural(today.shorts, "Short"), today.videos && plural(today.videos, "long video")]
                    .filter(Boolean).join(" · ")
                : "nothing yet"}
            </span>
          </Tile>
          <Tile label="Upload slots">
            <span style={big}>{used ?? "–"} <span style={{ fontSize: 17, color: "var(--muted)" }}>of {total ?? 5} used</span></span>
            <div className="bar" style={{ "--c": used >= total ? "var(--warn)" : "var(--go)" }}>
              {used > 0 && <i style={{ width: `${Math.min(100, (used / (total || 5)) * 100)}%` }} />}
            </div>
            <span className="muted" style={{ fontSize: 13 }}>Resets at {clock(today.quota_resets_at)}</span>
          </Tile>
          <Tile label="Going live next">
            {today.next_live ? (
              <>
                <span style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>{today.next_live.title}</span>
                <span style={{ fontSize: 13, color: "var(--go)" }}>Scheduled · {fmtWhen(today.next_live.publish_at)}</span>
              </>
            ) : (
              <span className="muted" style={{ fontSize: 13 }}>Nothing scheduled. Scheduled times show after the next YouTube sync.</span>
            )}
          </Tile>
          {today.private > 0 ? (
            <Tile label="Needs you" warn>
              <span style={{ ...big, color: "var(--warn)" }}>{today.private}</span>
              <span style={{ fontSize: 13, color: "#f1dfae" }}>
                {today.private === 1 ? "video is" : "videos are"} Private with no schedule. Nobody can see {today.private === 1 ? "it" : "them"}.
              </span>
              <div><Btn size="sm" onClick={() => setView("__allvideos")}>See which</Btn></div>
            </Tile>
          ) : (
            <Tile label="Scheduled">
              <span style={big}>{today.scheduled}</span>
              <span className="muted" style={{ fontSize: 13 }}>
                {today.scheduled ? `${today.scheduled === 1 ? "video is" : "videos are"} set to go live. Nothing is stuck in Private.` : "Nothing scheduled, and nothing stuck in Private."}
              </span>
            </Tile>
          )}
        </div>
      </section>

      <section className="cols c4" aria-label="Channel">
        <Stat label="Total views" value={fmtNum(channel.views)}
              note={channel.views_7d != null ? `${signed(channel.views_7d)} in the last 7 days` : "no week-old snapshot yet"} />
        <Stat label="Subscribers" value={fmtNum(channel.subscribers)}
              note={channel.subs_1d == null ? "" : channel.subs_1d === 0 ? "no change since yesterday" : `${signed(channel.subs_1d)} since yesterday`} />
        <Stat label="Likes" value={fmtNum(channel.likes)}
              note={channel.tracked_views ? `${((channel.likes / channel.tracked_views) * 100).toFixed(1)} per 100 views` : ""} />
        <Stat label="Comments" value={fmtNum(channel.comments)} note="across all videos" />
      </section>

      <div className="split">
        <section className="card wide" aria-labelledby="growth-h">
          <div className="card-head">
            <h2 id="growth-h">Total views over time</h2>
            <span className="spacer" />
            <span className="muted" style={{ fontSize: 13 }}>
              {channel.fetched_at ? `last synced ${fmtWhen(channel.fetched_at)}` : ""}
            </span>
          </div>
          <GrowthChart points={growth} markers={markers} />
        </section>
        <section className="card rail" aria-labelledby="rise-h" style={{ gap: 0 }}>
          <div className="card-head" style={{ marginBottom: 4 }}><h2 id="rise-h">Rising this week</h2></div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>views gained in the last 7 days</p>
          {rising.length === 0 && <p className="muted" style={{ fontSize: 13 }}>No gains recorded this week.</p>}
          {rising.map((v, i) => (
            <div key={v.key} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "10px 0",
                                      borderTop: i ? "1px solid var(--line)" : undefined }}>
              <span style={{ fontSize: 14 }}>{v.title}</span>
              <span className="num" style={{ color: "var(--go)", fontSize: 14 }}>{signed(v.gain_7d)}</span>
            </div>
          ))}
        </section>
      </div>

      <section className="card" aria-labelledby="latest-h">
        <div className="card-head">
          <h2 id="latest-h">Latest uploads</h2>
          <span className="spacer" />
          <Btn kind="ghost" size="sm" onClick={() => setView("__allvideos")}>All videos</Btn>
        </div>
        <div className="scroll">
          <table className="tbl">
            <thead>
              <tr><th>Video</th><th>Type</th><th>Posted</th><th>Status</th>
                <th className="r">Views</th><th className="r">Likes</th><th className="r">Comments</th></tr>
            </thead>
            <tbody>
              {latest.map((v) => (
                <tr key={v.key}>
                  <td className="t">{v.url ? <a href={v.url} target="_blank" rel="noreferrer" className="quiet-link">{v.title}</a> : v.title}</td>
                  <td><TypeChip v={v} /></td>
                  <td className="muted">{fmtWhen(v.uploaded_at, { time: false })}</td>
                  <td><StatusPill v={v} /></td>
                  <td className="r num"><N n={v.views} /></td>
                  <td className="r num"><N n={v.likes} /></td>
                  <td className="r num"><N n={v.comments} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {lf.length > 0 && (
        <section className="card" aria-labelledby="lf-h"
                 style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center", justifyContent: "space-between" }}>
          <div className="stack" style={{ gap: 4 }}>
            <h2 id="lf-h">Long-form videos</h2>
            <span className="muted" style={{ fontSize: 14 }}>
              {plural(lf.length, "video")} · {fmtNum(lfViews)} views · {plural(lfLikes, "like")} · {plural(lfComments, "comment")}.
              Their Shorts add {fmtNum(lfShorts)} views.
            </span>
          </div>
          <Btn onClick={() => setView("__lfstats")}>See each video</Btn>
        </section>
      )}
    </>
  );
}
