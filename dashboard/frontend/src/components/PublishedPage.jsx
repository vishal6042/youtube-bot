import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Btn, Empty, Icon, PageHeader, Pager, PlaylistChip, Search, Select, SkeletonRows, StatusChip, Thumb,
  fmtDuration, fmtNum, fmtWhen, usePaged,
} from "../ui.jsx";
import MoreMenu from "./upload/MoreMenu.jsx";
import "../screens/publish.css";

const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "most", label: "Most views" },
  { value: "fewest", label: "Fewest views" },
];
const VISIBILITY = [
  { value: "", label: "Any visibility" },
  { value: "public", label: "Public" },
  { value: "private", label: "Private" },
  { value: "unlisted", label: "Unlisted" },
];

const dayOf = (r) => (r.uploaded_at || "").slice(0, 10) || "unknown";

function timeOf(iso) {
  if (!iso || String(iso).length <= 10) return "";
  const d = new Date(String(iso).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/* "Today · Thursday 8 October", "Yesterday · …", else the full date. */
function dayLabel(key) {
  const d = new Date(key + "T00:00:00");
  if (Number.isNaN(d.getTime())) return "Date not recorded";
  const now = new Date();
  const midnight = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((midnight(now) - midnight(d)) / 86400000);
  const full = d.toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long",
    year: d.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
  return diff === 0 ? `Today · ${full}` : diff === 1 ? `Yesterday · ${full}` : full;
}

export default function PublishedPage({ onOpen, onUnmark, onWatch, onLink, confirm, toast }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [syncedAt, setSyncedAt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [series, setSeries] = useState("");
  const [visibility, setVisibility] = useState("");
  const [sort, setSort] = useState("newest");
  const [onlyNoLink, setOnlyNoLink] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/uploads"));
      setFailed(false);
    } catch (e) {
      setFailed(true);
      toast(e.message, true);
    }
  }, [toast]);

  // Stored snapshot only, so this costs no quota.
  const loadStats = useCallback(async () => {
    try { setSyncedAt((await api("/api/yt/stats")).channel?.fetched_at || null); } catch { /* optional */ }
  }, []);

  useEffect(() => { load(); loadStats(); }, [load, loadStats]);

  const sync = async () => {
    setBusy(true);
    try {
      const r = await api("/api/yt/sync", {});
      toast(`Refreshed from YouTube (${r.units_spent} quota units)`);
      await Promise.all([load(), loadStats()]);
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const uploads = data?.uploads || [];

  const playlists = useMemo(() => {
    const m = new Map();
    for (const r of uploads) if (!m.has(r.series)) m.set(r.series, r.playlist);
    return [...m.entries()];
  }, [uploads]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = uploads.filter((r) =>
      (!series || r.series === series) &&
      (!visibility || r.live?.privacy_status === visibility) &&
      (!onlyNoLink || !r.url) &&
      (!needle || `${r.title} ${r.key}`.toLowerCase().includes(needle)));
    if (sort === "newest") return out; // the server already sends newest first
    const dir = sort === "most" ? -1 : 1;
    // Videos with no count yet go last either way.
    return [...out].sort((a, b) => {
      const va = a.live?.views, vb = b.live?.views;
      if (va == null || vb == null) return (va == null) - (vb == null);
      return dir * (va - vb);
    });
  }, [uploads, q, series, visibility, onlyNoLink, sort]);

  const p = usePaged(rows, 15, `${q}|${series}|${visibility}|${onlyNoLink}|${sort}`);

  const privateCount = uploads.filter((r) => r.live?.privacy_status === "private").length;
  const noLink = data ? data.total - data.with_link : 0;
  const filtered = !!(q || series || visibility || onlyNoLink);
  const clearFilters = () => { setQ(""); setSeries(""); setVisibility(""); setOnlyNoLink(false); };

  const editLink = async (r) => {
    await onLink(r.key, r.title);
    load();
  };

  // Correction path: this is where a wrongly marked upload gets undone.
  const unmark = async (r) => {
    const ok = await confirm({
      title: "Mark as not uploaded?",
      message: `"${r.title}" goes back into the upload queue.`,
      detail: "Use this when a video was marked by mistake. The YouTube video, if there is one, is not touched.",
      confirmLabel: "Move back to queue", tone: "danger",
    });
    if (!ok) return;
    await onUnmark(r.key, r.title);
    load();
  };

  const row = (r) => {
    const vis = r.live?.privacy_status;
    return (
      <tr key={r.key}>
        <td>
          <div className="vid">
            <Thumb item={r} small />
            <div style={{ minWidth: 0 }}>
              <div className="t">{r.title || r.key}</div>
              <div className="k">{r.key}{r.episode != null ? ` · episode ${r.episode}` : ""}</div>
            </div>
          </div>
        </td>
        <td><PlaylistChip series={r.series} name={r.playlist} /></td>
        <td className="muted" style={{ whiteSpace: "nowrap" }}>
          {sort === "newest" ? (timeOf(r.uploaded_at) || fmtWhen(r.uploaded_at, { time: false })) : fmtWhen(r.uploaded_at, { time: false })}
        </td>
        <td className="r num">{fmtDuration(r.duration_sec)}</td>
        <td className="r num">
          {r.live?.views != null ? fmtNum(r.live.views) : <span className="faint">no data yet</span>}
        </td>
        <td>
          {vis ? <StatusChip state={vis} />
            : <span className="faint" style={{ fontSize: 13 }}>{r.url ? "Not checked yet" : "No link"}</span>}
        </td>
        <td>
          <div className="acts">
            <Btn kind="ghost" size="sm" icon="play" iconOnly={`Play ${r.title}`} onClick={() => onWatch(r)} />
            {r.url ? (
              <a className="btn icon sm ghost" href={r.url} target="_blank" rel="noopener noreferrer"
                 aria-label={`Open ${r.title} on YouTube`} title="Open on YouTube">
                <Icon name="external" />
              </a>
            ) : (
              <Btn kind="ghost" size="sm" icon="plus" iconOnly={`Add the YouTube link for ${r.title}`}
                   onClick={() => editLink(r)} />
            )}
            <MoreMenu label={`More actions for ${r.title}`} items={[
              { label: r.url ? "Edit link" : "Add link", icon: "edit", onClick: () => editLink(r) },
              r.exported && { label: "Open folder", icon: "folder", onClick: () => onOpen(r.exported) },
              { label: "Mark as not uploaded", icon: "undo", tone: "bad", onClick: () => unmark(r) },
            ]} />
          </div>
        </td>
      </tr>
    );
  };

  return (
    <>
      <PageHeader title="Published"
                  sub={"Everything on YouTube, with live view counts"
                     + (syncedAt ? ` · last refreshed ${fmtWhen(syncedAt)}` : "")}>
        <Btn icon="refresh" disabled={busy} onClick={sync}>
          {busy ? "Refreshing" : "Refresh from YouTube"}
        </Btn>
      </PageHeader>

      {privateCount > 0 && (
        <Banner tone="warn"
                title={privateCount === 1 ? "1 video is still Private" : `${privateCount} videos are still Private`}
                actions={
                  <Btn size="sm" aria-pressed={visibility === "private"}
                       onClick={() => setVisibility(visibility === "private" ? "" : "private")}>
                    {visibility === "private" ? "Show all videos" : "Show only private"}
                  </Btn>
                }>
          Nobody can see {privateCount === 1 ? "it" : "them"} until you switch {privateCount === 1 ? "it" : "them"} to
          Public in YouTube Studio.
        </Banner>
      )}

      <div className="rowf">
        <Search value={q} onChange={setQ} placeholder="Search title or key" label="Search published videos"
                style={{ flex: "1 1 260px" }} />
        <Select label="Playlist" value={series} onChange={setSeries}
                options={[{ value: "", label: "All playlists" },
                          ...playlists.map(([s, name]) => ({ value: s, label: name || s }))]} />
        <Select label="Visibility" value={visibility} onChange={setVisibility} options={VISIBILITY} />
        <Select label="Sort" value={sort} onChange={setSort} options={SORTS} />
        {/* Only worth showing when something actually lacks a link. */}
        {(noLink > 0 || onlyNoLink) && (
          <label className="rowf muted" style={{ gap: 8, minHeight: 44, cursor: "pointer" }}>
            <input type="checkbox" className="check" checked={onlyNoLink}
                   onChange={(e) => setOnlyNoLink(e.target.checked)} />
            Missing link only <span className="num faint">{noLink}</span>
          </label>
        )}
      </div>

      <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Published videos">
        {!data && !failed && <SkeletonRows rows={8} />}
        {!data && failed && (
          <Empty icon="alert" title="Could not load the published list"
                 action={<Btn size="sm" icon="refresh" onClick={load}>Try again</Btn>}>
            Make sure the dashboard server is running.
          </Empty>
        )}
        {data && !rows.length && (
          <Empty icon="published" title={filtered ? "No videos match" : "Nothing published yet"}
                 action={filtered ? <Btn size="sm" onClick={clearFilters}>Clear filters</Btn> : undefined}>
            {filtered ? "Try a different search or filter." : "Videos appear here once they are marked as uploaded."}
          </Empty>
        )}
        {data && rows.length > 0 && (
          <>
            <div className="scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Video</th><th>Playlist</th><th>Posted</th><th className="r">Length</th>
                    <th className="r">Views</th><th>Visibility</th>
                    <th style={{ width: 132 }}><span className="sr">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {p.slice.map((r, i) => (
                    <Fragment key={r.key}>
                      {sort === "newest" && (i === 0 || dayOf(p.slice[i - 1]) !== dayOf(r)) && (
                        <tr className="day"><td colSpan={7}>{dayLabel(dayOf(r))}</td></tr>
                      )}
                      {row(r)}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager p={p} noun="videos" sizes={[15, 30, 60]} style={{ padding: "14px 12px 0" }} />
          </>
        )}
      </section>
    </>
  );
}
