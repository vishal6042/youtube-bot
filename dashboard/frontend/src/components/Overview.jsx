import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Bar, Btn, Chip, Icon, PageHeader, PlaylistChip, Stat,
  fmtCompact, fmtDuration, fmtNum, fmtWhen,
} from "../ui.jsx";
import LiveRun from "./LiveRun.jsx";
import LongformLive from "./LongformLive.jsx";

const median = (xs) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/* The home screen answers one question first: what should I do next? */
export default function Overview({
  state, ideasCount, lines, titles, setView, onOpenSearch, onCancel, onCancelQueued,
}) {
  const [yt, setYt] = useState(null);
  const [uploads, setUploads] = useState(null);
  const [longform, setLongform] = useState(null);

  // Stored snapshots only: neither call spends YouTube quota.
  useEffect(() => {
    api("/api/yt/stats").then((r) => setYt(r.channel)).catch(() => {});
  }, []);
  useEffect(() => {
    api("/api/uploads").then((r) => setUploads(r.uploads || [])).catch(() => setUploads([]));
  }, [state.counts.uploaded]);

  // Long-form builds run outside the Shorts job queue, so they are polled on
  // their own: quickly while one is rendering, slowly otherwise.
  const lfLive = longform?.find((e) => e.build?.live);
  useEffect(() => {
    let alive = true;
    const load = () => api("/api/longform")
      .then((r) => alive && setLongform(r.episodes || []))
      .catch(() => {});
    load();
    const t = setInterval(load, lfLive ? 4000 : 20000);
    return () => { alive = false; clearInterval(t); };
  }, [!!lfLive]);  // eslint-disable-line react-hooks/exhaustive-deps

  const { counts, next_up: nextUp, upload_quota: quota, job, queue, history } = state;
  const rendering = (job ? 1 : 0) + queue.length;
  const slots = quota?.slots_left ?? null;

  const latest = useMemo(() => {
    if (!uploads) return [];
    // A video is judged against its own playlist, not the channel.
    const bySeries = {};
    for (const u of uploads) {
      if (u.live?.views != null) (bySeries[u.series] ||= []).push(u.live.views);
    }
    return [...uploads]
      .sort((a, b) => (b.uploaded_at || "").localeCompare(a.uploaded_at || ""))
      .slice(0, 5)
      .map((u) => ({ ...u, med: median(bySeries[u.series] || []) }));
  }, [uploads]);

  const privateCount = (uploads || []).filter((u) => u.live?.privacy_status === "private").length;
  const missingPlaylists = state.series.filter(
    (s) => !s.playlist_exists && s.total > 0 && s.uploaded < s.total
  );
  const stopped = state.upload_run?.stopped_reason;
  const failures = state.failures || [];
  const attention = missingPlaylists.length + (stopped ? 1 : 0) + (failures.length ? 1 : 0)
    + (privateCount ? 1 : 0);

  const last = history[0];
  const lastSecs = last?.started_at && last?.finished_at
    ? (new Date(last.finished_at) - new Date(last.started_at)) / 1000 : null;

  // Typical render time, from single-video jobs that completed.
  const typical = median(
    history
      .filter((h) => h.status === "done" && h.keys?.length === 1 && h.started_at && h.finished_at)
      .map((h) => (new Date(h.finished_at) - new Date(h.started_at)) / 1000)
      .filter((s) => s > 0)
  );

  const stages = [
    { label: "Ideas", value: ideasCount ?? "", note: "suggested, not added", to: "__ideas" },
    { label: "Planned", value: counts.missing, note: "never rendered", to: "__topics" },
    { label: "Rendering", value: rendering, note: rendering ? "in progress" : "nothing running", to: "__history" },
    { label: "In review", value: counts.rendered, note: "rendered, not approved", to: "__topics" },
    { label: "Ready to post", value: counts.ready, note: "in the upload queue", to: "__upload", hot: counts.ready > 0 },
    { label: "Published", value: counts.uploaded, note: "on YouTube", to: "__uploads" },
  ];

  // The primary card is whichever step unblocks the most right now.
  const post = {
    title: `${plural(counts.ready, "video is", "videos are")} ready to post`,
    body: [
      slots != null && (slots > 0
        ? `You have ${plural(slots, "upload slot")} left today.`
        : "Today's upload limit is used up; the next slots open tomorrow."),
      nextUp[0] && `Next in line: ${nextUp[0].title}.`,
    ].filter(Boolean).join(" "),
    cta: "Open upload queue", to: "__upload",
  };
  const render = {
    title: `${plural(counts.missing, "topic is", "topics are")} waiting to render`,
    body: `${typical ? `About ${fmtDuration(typical)} each. ` : ""}Ready videos cover roughly ${
      plural(counts.ready, "day")} of posting at one a day.`,
    cta: "Plan a render batch", to: "__launch",
  };
  const plan = {
    title: "Nothing is waiting",
    body: ideasCount ? `${plural(ideasCount, "idea")} are ready to add to the plan.` : "Add new topics to keep the pipeline moving.",
    cta: "Browse ideas", to: "__ideas",
  };
  const cards = [counts.ready > 0 && post, counts.missing > 0 && render].filter(Boolean);
  if (!cards.length) cards.push(plan);

  return (
    <>
      <PageHeader
        title="Overview"
        sub={`${new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })} · ${
          job || lfLive ? "rendering now" : "pipeline idle"}`}
      >
        <button type="button" className="search" onClick={onOpenSearch} style={{ cursor: "pointer", font: "inherit" }}>
          <Icon name="search" />
          <span style={{ flex: 1, textAlign: "left" }}>Search topics and videos</span>
          <span className="kbd">Ctrl K</span>
        </button>
        <Btn kind="primary" icon="play" onClick={() => setView("__launch")}>New render</Btn>
      </PageHeader>

      <section className="cols c2" aria-label="What to do next">
        {cards.map((c, i) => (
          <div key={c.to} className="card lift stack" style={{ gap: 10, borderColor: i === 0 ? "rgba(200,245,96,.4)" : undefined }}>
            <div><Chip tone={i === 0 ? "go" : "idle"}>{i === 0 ? "Do this next" : "Then"}</Chip></div>
            <h2 style={{ fontSize: 20 }}>{c.title}</h2>
            <p className="muted">{c.body}</p>
            <div className="rowf" style={{ marginTop: 6 }}>
              <Btn kind={i === 0 ? "primary" : ""} onClick={() => setView(c.to)}>{c.cta}</Btn>
            </div>
          </div>
        ))}
      </section>

      <LiveRun job={job} queue={queue} lines={lines} onCancel={onCancel} onCancelQueued={onCancelQueued} titles={titles} />
      <LongformLive ep={lfLive} onOpen={() => setView("__longform")} />

      <section className="card" aria-label="Pipeline">
        <div className="card-head">
          <h2>Pipeline</h2>
          <span className="muted" style={{ fontSize: 13 }}>every topic, by stage · select a stage to open it</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
          {stages.map((s) => (
            <button
              key={s.label} type="button" className="card lift" onClick={() => setView(s.to)}
              style={{ padding: 16, textAlign: "left", color: "inherit", font: "inherit", cursor: "pointer",
                       background: "var(--bg)", borderColor: s.hot ? "rgba(200,245,96,.4)" : undefined }}
            >
              <div className="stat">
                <div className="lbl" style={{ color: s.hot ? "var(--go)" : undefined }}>{s.label}</div>
                <div className="val">{s.value}</div>
                <div className="note">{s.note}</div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="cols c4" aria-label="Channel">
        <Stat label="Subscribers" value={yt ? fmtNum(yt.subscribers) : ""} note={yt ? `as of ${fmtWhen(yt.fetched_at)}` : "sync to load"} />
        <Stat label="Total views" value={yt ? fmtCompact(yt.views) : ""} note="all videos" />
        <Stat label="Videos on YouTube" value={yt ? fmtNum(yt.video_count) : ""} note={`${counts.uploaded} posted from here`} />
        <Stat label="Uploads today" value={quota ? `${quota.uploads_today} of ${quota.slots_total}` : ""}
              note={slots != null ? `${plural(slots, "slot")} left` : ""} />
      </section>

      <div className="split">
        <section className="card wide" aria-label="Latest posts">
          <div className="card-head">
            <h2>How the latest posts did</h2>
            <span className="spacer" />
            <Btn kind="ghost" size="sm" onClick={() => setView("__analytics")}>Open analytics</Btn>
          </div>
          <div className="scroll">
            <table className="tbl">
              <thead>
                <tr><th>Video</th><th>Playlist</th><th>Posted</th><th className="r">Views</th>
                  <th style={{ width: 160 }}>vs playlist median</th></tr>
              </thead>
              <tbody>
                {latest.map((u) => {
                  const v = u.live?.views;
                  const ratio = v != null && u.med ? v / u.med : null;
                  return (
                    <tr key={u.key}>
                      <td className="t">{u.title}</td>
                      <td><PlaylistChip series={u.series} name={u.playlist} /></td>
                      <td className="muted">{fmtWhen(u.uploaded_at, { time: false })}</td>
                      <td className="r num">{v != null ? fmtNum(v) : <span className="faint">no data yet</span>}</td>
                      <td>
                        {ratio != null && (
                          <Bar pct={ratio * 100}
                               color={ratio >= 1 ? undefined : ratio >= 0.5 ? "var(--warn)" : "var(--bad)"} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <div className="rail">
          {!job && (
            <section className="card" aria-label="Render status">
              <div className="card-head"><h2>Render</h2><Chip tone="idle">Idle</Chip></div>
              {last ? (
                <p className="muted" style={{ fontSize: 13 }}>
                  Last job: {titles?.[last.label] || <span className="num">{last.label}</span>}{" "}
                  {last.status === "done" ? "finished" : last.status} {fmtWhen(last.finished_at || last.created_at)}
                  {lastSecs ? ` in ${fmtDuration(lastSecs)}` : ""}.
                </p>
              ) : <p className="muted" style={{ fontSize: 13 }}>No renders yet.</p>}
              <div className="rowf" style={{ marginTop: 12 }}>
                <Btn size="sm" onClick={() => setView("__history")}>See all jobs</Btn>
              </div>
            </section>
          )}

          <section className="card" aria-label="Needs attention">
            <div className="card-head">
              <h2>Needs attention</h2>
              {attention > 0 && <Chip tone="warn" plain>{attention}</Chip>}
            </div>
            {attention === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>Nothing right now.</p>
            ) : (
              <div className="stack">
                {missingPlaylists.map((s) => (
                  <Banner key={s.series} title={`${s.playlist} isn't on YouTube yet`}
                          actions={<Btn size="sm" onClick={() => setView("__playlists")}>Fix</Btn>}>
                    Create the playlist before posting its {plural(s.total - s.uploaded, "video")}.
                  </Banner>
                ))}
                {privateCount > 0 && (
                  <Banner title={`${plural(privateCount, "video is", "videos are")} still Private`}
                          actions={<Btn size="sm" onClick={() => setView("__uploads")}>Review</Btn>}>
                    Nobody can see them until you switch them to Public in YouTube Studio.
                  </Banner>
                )}
                {stopped && (
                  <Banner tone="bad" title="Last upload run stopped"
                          actions={<Btn size="sm" onClick={() => setView("__upload")}>Review</Btn>}>
                    Nothing further was sent.
                  </Banner>
                )}
                {failures.length > 0 && (
                  <Banner tone="bad" title={`${plural(failures.length, "topic")} failed to render`}
                          actions={<Btn size="sm" onClick={() => setView("__history")}>Review</Btn>} />
                )}
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
