import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import {
  Bar, Btn, Empty, PageHeader, Pager, PlaylistChip, Search, Select, SkeletonRows, Stat,
  fmtCompact, fmtNum, fmtSecs, fmtWhen, playlistColor, usePaged,
} from "../ui.jsx";
import "../screens/learn.css";

/* Colour rule, kept from the old screen: the playlist palette is an identity
   system, not a chart palette (several pairs are too close to tell apart), so
   nothing here asks the reader to separate series by colour. Every bar carries
   its own label and value; colour only reinforces. */

const DAY = 86400000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
const BUCKET_LABEL = { "<=10s": "10s or under", "11-29s": "11 to 29s", "30s+": "30s or longer" };
const SORTS = [
  { value: "views", label: "Most views" },
  { value: "ctr", label: "Best click rate" },
  { value: "newest", label: "Newest" },
  { value: "shortest", label: "Shortest first" },
];

// Calendar days are parsed as UTC so a week never shifts with the local zone.
const parseDay = (iso) => new Date(String(iso).slice(0, 10) + "T00:00:00Z");
function dayLabel(iso) {
  const d = parseDay(iso);
  if (isNaN(d)) return String(iso ?? "");
  const year = d.getUTCFullYear() !== new Date().getFullYear() ? ` ${d.getUTCFullYear()}` : "";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${year}`;
}

/* Daily rows become Monday-start weeks: 130 daily bars are unreadable, and a
   Short's views arrive in a burst that a week holds in one bar. */
function toBars(daily) {
  const first = daily.findIndex((p) => p.views > 0);
  const points = first < 0 ? [] : daily.slice(first); // days before the channel had any views
  if (points.length <= 14) {
    return { unit: "day", partial: false,
             bars: points.map((p) => ({ start: p.day, views: p.views || 0, days: 1 })) };
  }
  const weeks = [];
  for (const p of points) {
    const d = parseDay(p.day);
    const start = new Date(d.getTime() - ((d.getUTCDay() + 6) % 7) * DAY).toISOString().slice(0, 10);
    let w = weeks[weeks.length - 1];
    if (!w || w.start !== start) weeks.push((w = { start, views: 0, days: 0 }));
    w.views += p.views || 0;
    w.days += 1;
  }
  return { unit: "week", bars: weeks, partial: weeks.length > 0 && weeks[weeks.length - 1].days < 7 };
}

function ViewsChart({ daily }) {
  const { unit, bars, partial } = useMemo(() => toBars(daily), [daily]);
  const max = Math.max(1, ...bars.map((b) => b.views));
  const fmt = bars.length > 12 ? fmtCompact : fmtNum;

  return (
    <section className="card wide" aria-label={`Views per ${unit}`}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <h2>Views per {unit}</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          {unit === "week"
            ? `channel views, weeks starting Monday${partial ? "; the last week is still filling" : ""}`
            : "channel views"}
        </span>
      </div>
      {!bars.length ? (
        <Empty icon="chart" title="No daily views yet">Update from YouTube to fill this chart.</Empty>
      ) : (
        <div className="wkchart" role="list">
          {bars.map((b, i) => (
            <div className="wk" role="listitem" key={b.start}
                 aria-label={`${unit === "week" ? "Week of " : ""}${dayLabel(b.start)}: ${fmtNum(b.views)} views`}>
              <span className={"num" + (b.views === max ? " best" : "")}>{fmt(b.views)}</span>
              <div className="wk-plot">
                {b.views > 0 && (
                  <div className="vbar"
                       style={{ height: `max(2px, ${(b.views / max) * 100}%)`,
                                animationDelay: `${Math.min(i * 0.04, 0.6)}s`,
                                "--c": b.views === max ? "var(--go)" : undefined }} />
                )}
              </div>
              <span>{dayLabel(b.start)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function LengthCard({ buckets }) {
  const max = Math.max(1, ...buckets.map((b) => b.median_views || 0));
  const longest = buckets.find((b) => b.bucket === "30s+");
  const shortest = buckets.find((b) => b.bucket === "<=10s");

  return (
    <section className="card" aria-label="Length and reach">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <h2>Length and reach</h2>
        <span className="muted" style={{ fontSize: 13 }}>median views by video length</span>
      </div>
      {!buckets.length ? (
        <p className="muted" style={{ fontSize: 13 }}>No video lengths recorded yet.</p>
      ) : (
        <div className="stack">
          {buckets.map((b) => (
            <div key={b.bucket}>
              <div className="bucket">
                <span>{BUCKET_LABEL[b.bucket] || b.bucket}</span>
                <Bar pct={((b.median_views || 0) / max) * 100} color="var(--info)" />
                <span className="num">{b.median_views != null ? fmtNum(Math.round(b.median_views)) : "n/a"}</span>
              </div>
              <div className="note-sm"><span className="num">{b.videos}</span> videos</div>
            </div>
          ))}
        </div>
      )}
      {shortest && longest && longest.median_views > 0 && (
        <p className="note-sm" style={{ marginTop: 14 }}>
          Videos of 10s or under get{" "}
          <b className="num" style={{ color: "var(--text)" }}>
            {(shortest.median_views / longest.median_views).toFixed(1)}x
          </b>{" "}
          the median views of those past 30s.
        </p>
      )}
    </section>
  );
}

function PlaylistTable({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.median_views || 0));
  return (
    <section className="card" aria-label="By playlist">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <h2>By playlist</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          median views, so one breakout video cannot carry a series
        </span>
      </div>
      {!rows.length ? (
        <Empty icon="playlists" title="No videos are matched to a playlist yet" />
      ) : (
        <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Playlist</th>
                <th className="r">Videos</th>
                <th className="r">Median views</th>
                <th style={{ width: "26%" }}><span className="sr">Median views, relative to the best playlist</span></th>
                <th className="r">Total views</th>
                <th className="r">Click rate</th>
                <th className="r">Subs per 1,000 views</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.series}>
                  <td><PlaylistChip series={r.series} name={r.playlist} /></td>
                  <td className="r num">{fmtNum(r.videos)}</td>
                  <td className="r num">{r.median_views != null ? fmtNum(Math.round(r.median_views)) : ""}</td>
                  <td><Bar pct={((r.median_views || 0) / max) * 100} color={playlistColor(r.series)} /></td>
                  <td className="r num">{fmtNum(r.total_views)}</td>
                  <td className="r num">{r.ctr != null ? `${r.ctr}%` : ""}</td>
                  <td className="r num">{r.subs_per_1k != null ? r.subs_per_1k.toFixed(2) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function VideoTable({ videos, onWatch }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("views");

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = videos.filter((v) =>
      !needle || [v.title, v.topic_key, v.playlist].some((x) => (x || "").toLowerCase().includes(needle)));
    const by = {
      views: (a, b) => (b.views ?? -1) - (a.views ?? -1),
      ctr: (a, b) => (b.ctr ?? -1) - (a.ctr ?? -1),
      newest: (a, b) => (b.published_at || "").localeCompare(a.published_at || ""),
      shortest: (a, b) => (a.duration_sec ?? Infinity) - (b.duration_sec ?? Infinity),
    }[sort];
    return list.sort(by);
  }, [videos, q, sort]);

  const p = usePaged(rows, 10, `${q}|${sort}`);

  return (
    <section className="card" aria-label="Top videos">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <h2>Top videos</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          the {videos.length} most viewed in this window
        </span>
        <span className="spacer" />
        <Search small value={q} onChange={setQ} label="Search videos" />
        <Select small label="Sort videos" value={sort} onChange={setSort} options={SORTS} />
      </div>
      {!rows.length ? (
        <Empty icon="search" title={videos.length ? "No video matches that search" : "No videos tracked yet"} />
      ) : (
        <div className="scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th>Video</th>
                <th>Playlist</th>
                <th>Published</th>
                <th className="r">Length</th>
                <th className="r">Views</th>
                <th className="r">Click rate</th>
                <th style={{ width: 52 }}><span className="sr">Play</span></th>
              </tr>
            </thead>
            <tbody>
              {p.slice.map((v, i) => (
                <tr key={v.video_id}>
                  <td className="num faint">{p.from + i}</td>
                  <td>
                    <div className="t">{v.title}</div>
                    {v.topic_key && <div className="k">{v.topic_key}</div>}
                  </td>
                  <td>
                    {v.series
                      ? <PlaylistChip series={v.series} name={v.playlist} />
                      : <span className="faint">none</span>}
                  </td>
                  <td className="num muted">{v.published_at ? dayLabel(v.published_at) : ""}</td>
                  <td className={"r num" + (v.duration_sec ? "" : " faint")}>
                    {v.duration_sec ? fmtSecs(v.duration_sec) : "not recorded"}
                  </td>
                  <td className="r num">{fmtNum(v.views)}</td>
                  <td className="r num">{v.ctr != null ? `${v.ctr}%` : ""}</td>
                  <td>
                    {v.topic_key && (
                      <Btn kind="ghost" size="sm" icon="play" iconOnly={`Play the local copy of ${v.title}`}
                           onClick={() => onWatch({ key: v.topic_key, title: v.title })} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager p={p} noun="videos" sizes={[10, 25]} />
    </section>
  );
}

export default function AnalyticsPage({ onWatch, toast }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    api("/api/analytics").then(setData).catch((e) => setErr(e.message));
  }, []);

  const syncNow = async () => {
    setSyncing(true);
    try {
      const r = await api("/api/analytics/sync", { days: 90 });
      toast?.(`Updated ${r.range[0]} to ${r.range[1]}: ${r.daily_rows} daily rows across ${r.videos} videos`);
      setData(await api("/api/analytics"));
    } catch (e) {
      toast?.(e.message, true);
    }
    setSyncing(false);
  };

  if (err) {
    return (
      <>
        <PageHeader title="Analytics" />
        <section className="card">
          <Empty icon="alert" title="Could not load analytics">{err}</Empty>
        </section>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader title="Analytics" sub="Loading" />
        <section className="card"><SkeletonRows rows={6} /></section>
      </>
    );
  }

  if (!data.available) {
    return (
      <>
        <PageHeader title="Analytics" />
        <section className="card">
          <Empty icon="analytics" title="Analytics are not available yet">
            {data.reason}
            <span className="note-sm" style={{ display: "block", marginTop: 8 }}>
              Drop YouTube Studio exports into <code>analytics_data/</code>, then
              run <code>python -m graph_bot.analytics import</code>.
            </span>
          </Empty>
        </section>
      </>
    );
  }

  const t = data.totals;
  const dash = (v, f = fmtNum) => (v == null ? "n/a" : f(v));

  return (
    <>
      <PageHeader title="Analytics"
                  sub={`${dayLabel(data.range.start)} to ${dayLabel(data.range.end)} · last updated ${fmtWhen(data.range.imported_at).replace(/^(Today|Yesterday)/, (m) => m.toLowerCase())}`}>
        <Btn icon={syncing ? undefined : "refresh"} disabled={syncing} aria-busy={syncing} onClick={syncNow}
             title="Daily views, watch time and subscribers come from the YouTube Analytics API. Impressions and click rate still need a Studio export.">
          {syncing && <span className="spin" aria-hidden="true" />}
          {syncing ? "Updating" : "Update from YouTube"}
        </Btn>
      </PageHeader>

      <section aria-label="Channel totals">
        <div className="cols" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          <Stat label="Views" value={dash(t.views, fmtCompact)} note="channel total" />
          <Stat label="Subscribers" value={t.subscribers == null ? "n/a" : `+${fmtNum(t.subscribers)}`}
                note="in this window" />
          <Stat label="Watch time" value={t.watch_hours == null ? "n/a" : `${t.watch_hours} h`}
                note={typeof t.avg_pct_viewed === "number" ? `${t.avg_pct_viewed}% of a video watched on average` : "hours watched"} />
          <Stat label="Thumbnail click rate" value={t.ctr == null ? "n/a" : `${t.ctr}%`}
                note={t.impressions == null ? undefined : `${fmtCompact(t.impressions)} impressions`} />
          <Stat label="Videos tracked" value={dash(t.videos)} note="with stats in this window" />
        </div>
        <p className="note-sm" style={{ marginTop: 10 }}>
          Channel figures are YouTube's own totals, not the sum of the per-video rows: unattributed
          views and subscribers do not belong to any single video.
        </p>
      </section>

      <div className="split">
        <ViewsChart daily={data.channel_daily || []} />
        <aside className="rail">
          <LengthCard buckets={data.length_buckets || []} />
        </aside>
      </div>

      <PlaylistTable rows={data.by_series || []} />
      <VideoTable videos={data.top_videos || []} onWatch={onWatch} />
    </>
  );
}
