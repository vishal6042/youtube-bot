import { Bar, Btn, Chip, Empty, PageHeader, PlaylistChip, SkeletonRows, Stat, fmtNum, fmtWhen } from "../ui.jsx";
import { N, StatusPill, fmtLen, usePerf } from "./perf/perf.jsx";

const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const mmss = (s) => (s == null ? "–" : fmtLen(s));

function Metric({ label, children, note }) {
  return (
    <div className="stat">
      <div className="lbl">{label}</div>
      <div className="val" style={{ fontSize: 26 }}>{children}</div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}

function VideoCard({ v, setView }) {
  const live = v.status === "live";
  const top = v.shorts.slice(0, 5);
  const maxS = Math.max(1, ...v.shorts.map((s) => s.views || 0));
  const m = v.milestones || {};
  const growth = [["1", "After 1 day"], ["3", "After 3 days"], ["7", "After 7 days"]]
    .filter(([k]) => m[k] != null)
    .map(([k, label]) => ({ label, n: m[k] }));
  const lastMilestone = growth.length ? growth[growth.length - 1].n : null;
  const since = lastMilestone != null && v.views != null ? v.views - lastMilestone : null;
  // Stalled: under 2% more views since its last milestone.
  const stalled = since != null && v.views > 0 && since < v.views * 0.02;
  return (
    <article className="card" aria-label={v.title} style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
      <img src={v.thumbnail} alt="" loading="lazy"
           style={{ width: 320, height: 180, objectFit: "cover", borderRadius: 10, flex: "0 0 auto", background: "var(--bg)" }} />
      <div className="stack" style={{ flex: "999 1 420px", minWidth: 0, gap: 14 }}>
        <div className="rowf" style={{ gap: 8 }}>
          <StatusPill v={v} />
          {live && v.posted_at && <Chip tone="idle" plain>Live since {fmtWhen(v.posted_at, { time: false })}</Chip>}
          <PlaylistChip series={v.series} name={v.playlist} />
          {v.duration_sec && <Chip tone="idle" plain>{fmtLen(v.duration_sec)}</Chip>}
        </div>
        <h2 style={{ fontSize: 20 }}>
          {v.url ? <a href={v.url} target="_blank" rel="noreferrer" className="quiet-link">{v.title}</a> : v.title}
        </h2>
        {v.views == null || (!live && !v.views) ? (
          <p className="muted">Stats appear once it is live and the next YouTube sync runs.</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 14 }}>
            <Metric label="Views"><N n={v.views} /></Metric>
            <Metric label="Likes"><N n={v.likes} /></Metric>
            <Metric label="Comments"><N n={v.comments} /></Metric>
            <div className="stat">
              <div className="lbl">Watched on average</div>
              <div className="val" style={{ fontSize: 26 }}>{mmss(v.avg_view_sec)}</div>
              {v.avg_pct_viewed != null && (
                <>
                  <Bar pct={v.avg_pct_viewed} color="#5ee0c8" style={{ marginTop: 6 }} />
                  <div className="note">{v.avg_pct_viewed.toFixed(1)}% of the video</div>
                </>
              )}
            </div>
          </div>
        )}
        {growth.length > 0 && (
          <div className="rowf" style={{ gap: 18, fontSize: 13 }}>
            {growth.map((g) => (
              <span key={g.label} className="muted">{g.label}: <b className="num" style={{ color: "var(--text)" }}>{fmtNum(g.n)}</b></span>
            ))}
            {since != null && (
              <span className="muted">Since then: <b className="num" style={{ color: stalled ? "var(--warn)" : "var(--go)" }}>
                {since >= 0 ? "+" : ""}{fmtNum(since)}</b>{stalled ? " (stalled)" : ""}</span>
            )}
          </div>
        )}
        <div className="rowf" style={{ gap: 10 }}>
          {v.shorts.length < v.shorts_planned && (
            <Btn kind={v.shorts.length ? "" : "primary"} onClick={() => setView("__launch")}>
              {v.shorts.length ? "Post more of its Shorts" : "Make its Shorts"}
            </Btn>
          )}
          {v.video_id && (
            <a className="btn" href={`https://studio.youtube.com/video/${v.video_id}/edit`} target="_blank" rel="noreferrer">
              Open in Studio
            </a>
          )}
        </div>
      </div>
      <div style={{ flex: "1 1 340px", minWidth: 0, background: "var(--bg)", border: "1px solid var(--line)", borderRadius: 12, padding: 16 }}>
        <div className="card-head" style={{ marginBottom: 8 }}>
          <h3 style={{ fontSize: 14 }}>Its Shorts · {v.shorts.length} of {v.shorts_planned} posted</h3>
          <span className="spacer" />
          <span className="num muted" style={{ fontSize: 13 }}>{fmtNum(v.shorts_views)} views · {plural(v.shorts_likes, "like")}</span>
        </div>
        {v.shorts.length === 0 && <p className="muted" style={{ fontSize: 13 }}>None posted yet.</p>}
        {top.map((s) => (
          <div key={s.key} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 110px 64px", gap: 10, alignItems: "center", padding: "6px 0", fontSize: 13 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.title}>{s.title}</span>
            <Bar pct={((s.views || 0) / maxS) * 100} color="#f5a524" />
            <span className="num" style={{ textAlign: "right", color: s.status === "private" ? "var(--warn)" : undefined }}>
              {s.status === "private" ? "Private" : s.views == null ? "–" : fmtNum(s.views)}
            </span>
          </div>
        ))}
        {v.shorts.length > top.length && (
          <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>and {plural(v.shorts.length - top.length, "more Short")}</p>
        )}
        <p style={{ fontSize: 13, marginTop: 10 }} className="muted">
          Total reach, video plus Shorts: <b className="num" style={{ color: "var(--go)" }}>{fmtNum(v.reach)}</b>
        </p>
      </div>
    </article>
  );
}

/* Each long-form video with the Shorts cut from it: views, likes, comments,
   how much of it people watch, and how its views grew. */
export default function LongformStatsPage({ setView }) {
  const { perf, error } = usePerf();
  if (error) return <Empty icon="analytics" title="Stats are unavailable">{error}</Empty>;
  if (!perf) return <SkeletonRows rows={6} />;
  const lf = perf.longform;
  const live = lf.filter((v) => v.status === "live");
  const views = lf.reduce((a, v) => a + (v.views || 0), 0);
  const likes = lf.reduce((a, v) => a + (v.likes || 0), 0);
  const comments = lf.reduce((a, v) => a + (v.comments || 0), 0);
  const shortViews = lf.reduce((a, v) => a + (v.shorts_views || 0), 0);
  const shortsLive = lf.reduce((a, v) => a + v.shorts.filter((s) => s.status === "live").length, 0);
  const watched = live.filter((v) => v.avg_pct_viewed != null);
  const avgPct = watched.length ? watched.reduce((a, v) => a + v.avg_pct_viewed, 0) / watched.length : null;
  const avgSec = watched.length ? watched.reduce((a, v) => a + v.avg_view_sec, 0) / watched.length : null;

  return (
    <>
      <PageHeader title="Long-form results"
                  sub="Each video with the Shorts cut from it. Views, likes and comments from the last YouTube sync; watch time from the last analytics import." />
      <section className="cols c4" aria-label="Totals">
        <Stat label="Videos" value={lf.length} note={`${live.length} live · ${lf.length - live.length} not live yet`} />
        <Stat label="Views on the videos" value={fmtNum(views)} note={`${plural(likes, "like")} · ${plural(comments, "comment")}`} />
        <Stat label="Views on their Shorts" value={fmtNum(shortViews)} note={`${plural(shortsLive, "Short")} live`} />
        <Stat label="Watched on average" value={avgPct != null ? `${Math.round(avgPct)}%` : "–"}
              note={avgSec != null ? `about ${fmtLen(avgSec)} per view` : "after the next analytics import"} />
      </section>
      {lf.length === 0 && <Empty icon="screen" title="No long-form videos posted yet" />}
      {lf.map((v) => <VideoCard key={v.key} v={v} setView={setView} />)}
    </>
  );
}
