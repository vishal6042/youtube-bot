import { useMemo, useState } from "react";
import { Empty, PageHeader, Pager, PlaylistChip, Search, Seg, Select, SkeletonRows, fmtWhen, usePaged } from "../ui.jsx";
import { N, StatusPill, TypeChip, signed, usePerf } from "./perf/perf.jsx";

const COLS = [
  { key: "views", label: "Views" },
  { key: "likes", label: "Likes" },
  { key: "like_rate", label: "Like rate" },
  { key: "comments", label: "Comments" },
  { key: "gain_7d", label: "Last 7 days" },
];
const DAY = 86400000;

/* Every posted video in one table: filter by type, playlist, date and status;
   sort by any number. */
export default function AllVideosPage() {
  const { perf, error } = usePerf();
  const [kind, setKind] = useState("all");
  const [series, setSeries] = useState("all");
  const [when, setWhen] = useState("any");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ key: "views", dir: -1 });

  const rows = useMemo(() => (perf?.videos || []).map((v) => ({
    // Under 50 views a like rate is noise (1 like on 1 view reads as 100%).
    ...v, like_rate: v.views >= 50 ? (v.likes || 0) / v.views : null,
  })), [perf]);

  const playlists = useMemo(() => {
    const m = new Map();
    for (const v of rows) if (v.series) m.set(v.series, v.playlist || v.series);
    return [...m].sort((a, b) => a[1].localeCompare(b[1]));
  }, [rows]);

  const shown = useMemo(() => {
    const now = Date.now();
    const cut = { today: 1, week: 7, month: 30 }[when];
    const needle = q.trim().toLowerCase();
    const out = rows.filter((v) =>
      (kind === "all" || v.kind === kind)
      && (series === "all" || v.series === series)
      && (status === "all" || v.status === status)
      && (!cut || (v.uploaded_at && now - new Date(v.uploaded_at).getTime() < cut * DAY))
      && (!needle || (v.title || "").toLowerCase().includes(needle) || v.key.includes(needle)));
    const { key, dir } = sort;
    return out.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;   // no stats yet: always last
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * dir;
    });
  }, [rows, kind, series, status, when, q, sort]);

  const p = usePaged(shown, 25, [kind, series, status, when, q, sort.key, sort.dir].join("|"));

  if (error) return <Empty icon="analytics" title="Stats are unavailable">{error}</Empty>;
  if (!perf) return <SkeletonRows rows={10} />;

  const count = (k) => rows.filter((v) => k === "all" || v.kind === k).length;
  const sortBy = (key) => setSort((s) => ({ key, dir: s.key === key ? -s.dir : -1 }));
  const th = (c) => (
    <th key={c.key} className="r" aria-sort={sort.key === c.key ? (sort.dir < 0 ? "descending" : "ascending") : "none"}>
      <button type="button" onClick={() => sortBy(c.key)}
              style={{ background: "none", border: 0, padding: 0, font: "inherit", cursor: "pointer",
                       color: sort.key === c.key ? "var(--go)" : "inherit" }}>
        {c.label}{sort.key === c.key ? (sort.dir < 0 ? " ▾" : " ▴") : ""}
      </button>
    </th>
  );

  return (
    <>
      <PageHeader title="All videos"
                  sub={`${rows.length} videos · stats from the last YouTube sync${perf.overview.channel.fetched_at ? ", " + fmtWhen(perf.overview.channel.fetched_at) : ""} · select a column to sort`} />
      <div className="rowf" style={{ gap: 12, alignItems: "center" }}>
        <Seg label="Type" value={kind} onChange={setKind}
             options={[{ value: "all", label: "All", count: count("all") },
                       { value: "short", label: "Shorts", count: count("short") },
                       { value: "video", label: "Long-form", count: count("video") }]} />
        <Select label="Playlist" value={series} onChange={setSeries}
                options={[{ value: "all", label: "All playlists" }, ...playlists.map(([value, label]) => ({ value, label }))]} />
        <Select label="Posted" value={when} onChange={setWhen}
                options={[{ value: "any", label: "Any time" }, { value: "today", label: "Today" },
                          { value: "week", label: "Last 7 days" }, { value: "month", label: "Last 30 days" }]} />
        <Select label="Status" value={status} onChange={setStatus}
                options={[{ value: "all", label: "Any status" }, { value: "live", label: "Live" },
                          { value: "scheduled", label: "Scheduled" }, { value: "private", label: "Private" },
                          { value: "waiting", label: "Waiting for stats" }]} />
        <Search value={q} onChange={setQ} placeholder="Search titles" style={{ flex: "1 1 220px" }} />
      </div>
      <section className="card" style={{ padding: 8 }}>
        {shown.length === 0 ? (
          <Empty icon="search" title="No videos match these filters" />
        ) : (
          <>
            <div className="scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th className="r">#</th><th>Video</th><th>Type</th><th>Playlist</th>
                    <th>
                      <button type="button" onClick={() => sortBy("uploaded_at")}
                              style={{ background: "none", border: 0, padding: 0, font: "inherit", cursor: "pointer",
                                       color: sort.key === "uploaded_at" ? "var(--go)" : "inherit" }}>
                        Posted{sort.key === "uploaded_at" ? (sort.dir < 0 ? " ▾" : " ▴") : ""}
                      </button>
                    </th>
                    <th>Status</th>
                    {COLS.map(th)}
                  </tr>
                </thead>
                <tbody>
                  {p.slice.map((v, i) => (
                    <tr key={v.key}>
                      <td className="r num faint">{p.from + i}</td>
                      <td className="t">{v.url ? <a href={v.url} target="_blank" rel="noreferrer" className="quiet-link">{v.title}</a> : v.title}</td>
                      <td><TypeChip v={v} /></td>
                      <td><PlaylistChip series={v.series} name={v.playlist} /></td>
                      <td className="muted">{fmtWhen(v.uploaded_at, { time: false })}</td>
                      <td><StatusPill v={v} /></td>
                      <td className="r num"><N n={v.views} /></td>
                      <td className="r num"><N n={v.likes} /></td>
                      <td className="r num">{v.like_rate == null ? <span className="faint">–</span> : `${(v.like_rate * 100).toFixed(1)}%`}</td>
                      <td className="r num"><N n={v.comments} /></td>
                      <td className="r num" style={{ color: v.gain_7d > 0 ? "var(--go)" : "var(--faint)" }}>
                        {v.gain_7d == null ? "–" : signed(v.gain_7d)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager p={p} noun="videos" sizes={[25, 50, 100]} style={{ padding: 12 }} />
          </>
        )}
      </section>
    </>
  );
}
