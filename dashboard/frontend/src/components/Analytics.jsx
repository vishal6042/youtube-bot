import { useEffect, useMemo, useRef, useState } from "react";
import Chip from "./Chip.jsx";
import { api, seriesChip } from "../api.js";

/* Analytics screen, fed by the Postgres warehouse (graph_bot.analytics).
 *
 * Colour rule: the playlist palette is an identity system for chips and cover
 * art, not a chart palette — sports-green vs charts-lie-rose is only ΔE 4.7 for
 * deuteranopia, and india-orange vs money-gold is 9.6 even with normal vision.
 * So no chart here asks the reader to tell series apart BY COLOUR: every bar is
 * directly labelled with its playlist name and the colour is redundant
 * reinforcement, the trend line is a single hue, and the length buckets are
 * ordinal so they use one hue stepped light→dark.
 */

const AXIS = "rgba(72, 118, 190, 0.22)";   // recessive grid
const LINE = "#38e1ff";                     // single-series hue
const BUCKET_HUES = ["#9beeff", "#4fd4f2", "#1f93b8"];  // one hue, light → dark

function fmtNum(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(Math.round(n));
}

function fmtDay(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/* ── channel views over time: one series, so no legend — the title names it ── */
function TrendChart({ points }) {
  const [hover, setHover] = useState(null);
  const ref = useRef(null);
  const W = 960, H = 250, PAD = { t: 30, r: 18, b: 26, l: 46 };

  const { path, area, xy, max } = useMemo(() => {
    const max = Math.max(1, ...points.map((p) => p.views));
    const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
    const xy = points.map((p, i) => [
      PAD.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw),
      PAD.t + ih - (p.views / max) * ih,
    ]);
    const path = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    const area = `${path}L${xy.at(-1)[0].toFixed(1)},${PAD.t + ih}L${xy[0][0].toFixed(1)},${PAD.t + ih}Z`;
    return { path, area, xy, max };
  }, [points]);

  const ticks = [0, 0.5, 1].map((f) => ({
    v: Math.round(max * f),
    y: PAD.t + (H - PAD.t - PAD.b) * (1 - f),
  }));

  const onMove = (e) => {
    const r = ref.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    for (let i = 1; i < xy.length; i++) {
      if (Math.abs(xy[i][0] - x) < Math.abs(xy[best][0] - x)) best = i;
    }
    setHover(best);
  };

  const peak = points.reduce((a, p, i) => (p.views > points[a].views ? i : a), 0);

  return (
    <div className="an-chart">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="an-svg"
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t.v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke={AXIS} />
            <text x={PAD.l - 8} y={t.y + 4} className="an-tick" textAnchor="end">{fmtNum(t.v)}</text>
          </g>
        ))}
        <defs>
          <linearGradient id="an-fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={LINE} stopOpacity="0.28" />
            <stop offset="100%" stopColor={LINE} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#an-fade)" />
        <path d={path} fill="none" stroke={LINE} strokeWidth="2"
              strokeLinejoin="round" vectorEffect="non-scaling-stroke" />

        {/* The peak is worth naming; every other point is on hover only. The
            label flips below the point when it would clip the top edge, and
            anchors inward near either side so it never runs off. */}
        <circle cx={xy[peak][0]} cy={xy[peak][1]} r="4" fill={LINE} />
        <text
          x={xy[peak][0]}
          y={xy[peak][1] - 10 < 14 ? xy[peak][1] + 19 : xy[peak][1] - 10}
          className="an-peak"
          textAnchor={xy[peak][0] < 40 ? "start" : xy[peak][0] > W - 40 ? "end" : "middle"}
        >
          {fmtNum(points[peak].views)}
        </text>

        {points.length > 1 && [0, points.length - 1].map((i) => (
          <text key={i} x={xy[i][0]} y={H - 8} className="an-tick"
                textAnchor={i ? "end" : "start"}>{fmtDay(points[i].day)}</text>
        ))}

        {hover != null && (
          <g>
            <line x1={xy[hover][0]} x2={xy[hover][0]} y1={PAD.t} y2={H - PAD.b}
                  stroke={LINE} strokeOpacity="0.45" />
            <circle cx={xy[hover][0]} cy={xy[hover][1]} r="4.5" fill={LINE}
                    stroke="#090e1a" strokeWidth="2" />
          </g>
        )}
      </svg>
      <div className="an-tip" style={{ visibility: hover == null ? "hidden" : "visible" }}>
        {hover != null && (
          <>
            <b>{fmtNum(points[hover].views)}</b> views
            <span> · {fmtDay(points[hover].day)}</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ── median views by playlist: identity is the label, colour is reinforcement ── */
function SeriesBars({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.median_views || 0));
  return (
    <div className="an-bars">
      {rows.map((r) => (
        <div className="an-bar-row" key={r.series}>
          <span className="an-bar-label">
            <i className={"an-dot " + seriesChip(r.series)} />
            {r.playlist}
          </span>
          <span className="an-bar-track">
            <span
              className={"an-bar-fill " + seriesChip(r.series)}
              style={{ width: `${((r.median_views || 0) / max) * 100}%` }}
            />
          </span>
          <span className="an-bar-val">{fmtNum(r.median_views)}</span>
          <span className="an-bar-meta">{r.videos} videos · CTR {r.ctr ?? "—"}%</span>
        </div>
      ))}
    </div>
  );
}

export default function Analytics({ onBack, onWatch, toast }) {
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
      toast?.(`✅ Synced ${r.range[0]} → ${r.range[1]}: ${r.daily_rows} daily rows across ${r.videos} videos`);
      setData(await api("/api/analytics"));
    } catch (e) {
      toast?.(e.message, true);
    }
    setSyncing(false);
  };

  if (err) return <div className="panel"><div className="empty">Could not load analytics: {err}</div></div>;
  if (!data) return <div className="panel"><div className="empty">Loading analytics…</div></div>;

  if (!data.available) {
    return (
      <div className="an">
        <section className="panel">
          <div className="detail-head">
            <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
            <div className="pl-name">ANALYTICS</div>
          </div>
        </section>
        <section className="panel">
          <div className="an-setup">
            <p className="an-setup-title">The analytics warehouse isn't available.</p>
            <p className="muted">{data.reason}</p>
            <p className="muted">
              Drop YouTube Studio exports into <code>analytics_data/</code>, then run
              {" "}<code>python -m graph_bot.analytics import</code>.
            </p>
          </div>
        </section>
      </div>
    );
  }

  const t = data.totals;
  const longest = data.length_buckets.find((b) => b.bucket === "30s+");
  const shortest = data.length_buckets.find((b) => b.bucket === "<=10s");
  const bMax = Math.max(1, ...data.length_buckets.map((b) => b.median_views || 0));

  return (
    <div className="an">
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">ANALYTICS</div>
            <div className="pl-series">
              {data.range.start} → {data.range.end} · from the warehouse, imported{" "}
              {data.range.imported_at.slice(0, 10)}
            </div>
          </div>
          <button className="btn save-btn" disabled={syncing} onClick={syncNow}
                  title="YouTube Analytics API — daily views, watch time, subscribers. Impressions/CTR still need a Studio zip export.">
            {syncing ? "⏳ SYNCING…" : "📡 SYNC FROM YOUTUBE"}
          </button>
        </div>
      </section>

      {/* ---- headline numbers: no plot, so no chart ---- */}
      <section className="panel">
        <div className="an-tiles">
          <div className="an-tile"><span>VIEWS</span><b>{fmtNum(t.views)}</b><em>channel total</em></div>
          <div className="an-tile"><span>SUBSCRIBERS</span><b>+{t.subscribers ?? "—"}</b><em>in this window</em></div>
          <div className="an-tile"><span>WATCH TIME</span><b>{t.watch_hours ?? "—"}</b><em>hours</em></div>
          <div className="an-tile"><span>THUMBNAIL CTR</span><b>{t.ctr ?? "—"}%</b><em>{fmtNum(t.impressions)} impressions</em></div>
          <div className="an-tile"><span>VIDEOS</span><b>{t.videos}</b><em>tracked</em></div>
        </div>
        <p className="an-note">
          Channel figures are YouTube's own totals, not the sum of the per-video rows —
          unattributed views and subscribers do not belong to any single video.
        </p>
      </section>

      {/* ---- change over time ---- */}
      <section className="panel">
        <div className="an-head">
          <span className="panel-title">CHANNEL VIEWS PER DAY</span>
          <span className="an-head-meta">{data.channel_daily.length} days</span>
        </div>
        <TrendChart points={data.channel_daily} />
      </section>

      {/* ---- magnitude by identity ---- */}
      <section className="panel">
        <div className="an-head">
          <span className="panel-title">MEDIAN VIEWS BY PLAYLIST</span>
          <span className="an-head-meta">median, so one breakout video can't carry a series</span>
        </div>
        <SeriesBars rows={data.by_series} />
      </section>

      {/* ---- ordered buckets: one hue, light → dark ---- */}
      <section className="panel">
        <div className="an-head">
          <span className="panel-title">LENGTH VS REACH</span>
          <span className="an-head-meta">median views by video length</span>
        </div>
        <div className="an-buckets">
          {data.length_buckets.map((b, i) => (
            <div className="an-bucket" key={b.bucket}>
              <div className="an-bucket-plot">
                <div className="an-bucket-fill"
                     style={{ height: `${((b.median_views || 0) / bMax) * 100}%`,
                              background: BUCKET_HUES[i] }} />
              </div>
              <b>{fmtNum(b.median_views)}</b>
              <span>{b.bucket}</span>
              <em>{b.videos} videos</em>
            </div>
          ))}
        </div>
        {shortest && longest && longest.median_views > 0 && (
          <p className="an-note">
            Videos of 10s or under pull{" "}
            <b>{(shortest.median_views / longest.median_views).toFixed(1)}×</b> the median
            views of those past 30s. Length is the strongest lever in this data.
          </p>
        )}
      </section>

      {/* ---- the table view: also the accessible fallback for every chart ---- */}
      <section className="panel">
        <div className="an-head">
          <span className="panel-title">TOP VIDEOS</span>
          <span className="an-head-meta">by views in this window</span>
        </div>
        <div className="an-table" role="table">
          <div className="an-tr an-th" role="row">
            <span>#</span><span>Title</span><span>Playlist</span>
            <span className="num">Length</span><span className="num">Views</span><span className="num">CTR</span>
          </div>
          {data.top_videos.map((v, i) => (
            <div className="an-tr" role="row" key={v.video_id}>
              <span className="an-rank">{String(i + 1).padStart(2, "0")}</span>
              <span className="an-vtitle" title={v.title}>
                {v.title}
                {v.topic_key && (
                  <button className="an-play" title="Watch the local copy"
                          onClick={() => onWatch({ key: v.topic_key, title: v.title })}>▶</button>
                )}
              </span>
              <span>
                {v.series
                  ? <Chip cls={seriesChip(v.series)}>{v.playlist}</Chip>
                  : <span className="muted">—</span>}
              </span>
              <span className="num">{v.duration_sec ? `${v.duration_sec}s` : "—"}</span>
              <span className="num"><b>{fmtNum(v.views)}</b></span>
              <span className="num">{v.ctr != null ? `${v.ctr}%` : "—"}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
