import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Btn, Chip, Empty, MODE_LABEL, PageHeader, Pager, PlaylistChip, Search, Select,
  SkeletonRows, fmtDuration, usePaged,
} from "../ui.jsx";
import LiveRun from "./LiveRun.jsx";
import FromVideos from "./render/FromVideos.jsx";
import "../screens/produce.css";

/* Strategies are intents, not orderings: "re-cut" deliberately targets videos
   that are already public, so it is opt-in and labelled wherever it appears. */
const MODES = [
  { id: "new", label: "New topics", blurb: "Never rendered. Nothing can be overwritten.",
    empty: "Nothing new to render. Accept a suggestion in Ideas and it appears here." },
  { id: "staged", label: "Improve unposted", blurb: "Re-render videos that are not on YouTube yet.",
    empty: "No rendered videos are waiting to be posted." },
  { id: "recut", label: "Re-cut published",
    blurb: "Already live. Makes a new file; the posted video is untouched.",
    empty: "No published videos match these options." },
];

function fmtMins(secs) {
  if (!secs) return "";
  const m = Math.round(secs / 60);
  return m < 1 ? "under 1 min" : `~${m} min`;
}

function daysAgo(iso) {
  if (!iso) return null;
  // Whole calendar days between that date and today (both at local midnight),
  // so something made this evening is "today", not "yesterday".
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = Math.round((today.getTime() - new Date(iso + "T00:00:00").getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function PlanRow({ t, checked, onToggle, onRevert }) {
  const last = t.last_rendered ? `${daysAgo(t.last_rendered)}` : "Never";
  const madeToday = daysAgo(t.last_rendered) === "today";
  const more = [
    t.episode != null && `Episode ${t.episode}`,
    t.mood && `${t.mood} music`,
    [t.source, t.fetcher].filter(Boolean).join(" · "),
  ].filter(Boolean).join("\n");

  return (
    <tr title={more} onClick={t.already_queued ? undefined : onToggle}
        style={{ cursor: t.already_queued ? "default" : "pointer" }}
        aria-selected={checked}>
      <td onClick={(e) => e.stopPropagation()}>
        <input className="check" type="checkbox" checked={checked} disabled={t.already_queued}
               aria-label={`Render ${t.title || t.key}`} onChange={onToggle} />
      </td>
      <td>
        <div className="t">{t.title || t.key}</div>
        <div className="k">{t.key}</div>
      </td>
      <td>
        <div className="rowf" style={{ gap: 6 }}>
          <PlaylistChip series={t.series} name={t.playlist} />
          {!t.playlist_exists && (
            <Chip tone="bad" title="This playlist does not exist on YouTube yet">No playlist yet</Chip>
          )}
        </div>
      </td>
      <td className="muted">
        {t.chart_mode ? (MODE_LABEL[t.chart_mode] || t.chart_mode) : ""}{t.narrated ? " · narrated" : ""}
      </td>
      <td>
        {t.already_queued ? <Chip tone="idle">Already queued</Chip>
          : t.uploaded ? (
            <Chip tone="warn" title="Already public on YouTube. Re-rendering replaces your local copy only.">
              Already live
            </Chip>
          ) : t.exported ? <Chip tone="info" title="Rendered but not posted yet">Not posted yet</Chip>
          : t.staged_new ? <Chip tone="go">New</Chip> : null}
      </td>
      <td className="muted">
        {madeToday ? <Chip tone="go" title="Rendered today">Made today</Chip> : last}
        {t.duration_sec != null ? ` · ${fmtDuration(t.duration_sec)}` : ""}
      </td>
      <td onClick={(e) => e.stopPropagation()}>
        {t.staged_new && !t.already_queued && (
          <Btn kind="ghost" size="sm" icon="trash"
               iconOnly={`Delete ${t.title || t.key} from the topic list (never rendered)`}
               onClick={onRevert} />
        )}
      </td>
    </tr>
  );
}

export default function RenderPage({ series = [], job, queue = [], lines, onRenderBatch, onRevertTopic,
                                     onCancel, onCancelQueued, confirm, busy, pipelineVersion,
                                     videoTitles = {} }) {
  const [mode, setMode] = useState("new");
  const [pickedSeries, setPickedSeries] = useState("");
  const [q, setQ] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [autoPicked, setAutoPicked] = useState(false);
  // Ticked videos, by key. Kept across search and playlist filters, so you can
  // pick from several playlists and render them together.
  const [selected, setSelected] = useState(() => new Set());
  const reqRef = useRef(0);

  const loadPlan = useCallback(async () => {
    const req = ++reqRef.current;
    setLoading(true);
    try {
      // Every matching video; searching, filtering and ticking happen in the page.
      const p = await api(`/api/plan?${new URLSearchParams({ batch: "1000", mode })}`);
      if (req !== reqRef.current) return;   // a newer request superseded this one
      // First load only: if there is no new work, fall back to the next most
      // useful strategy rather than opening on an empty plan.
      if (!autoPicked && mode === "new" && p.counts?.new === 0) {
        setAutoPicked(true);
        setMode(p.counts.staged > 0 ? "staged" : "recut");
        return;
      }
      setAutoPicked(true);
      setPlan(p);
    } catch {
      if (req === reqRef.current) setPlan(null);
    }
    if (req === reqRef.current) setLoading(false);
    // pipelineVersion changes whenever a job starts or finishes, so a finished
    // render drops out of the plan instead of lingering.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, autoPicked, pipelineVersion]);

  useEffect(() => { loadPlan(); }, [loadPlan]);
  // A different kind of work is a different list; ticks do not carry over.
  useEffect(() => { setSelected(new Set()); }, [mode]);

  const titles = useMemo(() => {
    const map = {};
    for (const s of series) for (const i of s.items || []) if (i.title) map[i.key] = i.title;
    for (const t of plan?.topics || []) if (t.title) map[t.key] = t.title;
    return { ...videoTitles, ...map };
  }, [series, plan, videoTitles]);

  const all = plan?.topics || [];
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter((t) => (!pickedSeries || t.series === pickedSeries)
      && (!needle || `${t.title} ${t.key}`.toLowerCase().includes(needle)));
  }, [all, pickedSeries, q]);
  const paged = usePaged(shown, 10, `${mode}|${pickedSeries}|${q}`);
  // What will run: the ticked videos, in list order (never rendered first, then oldest).
  const topics = all.filter((t) => selected.has(t.key) && !t.already_queued);
  const firstLoad = loading && !plan;
  const nothing = topics.length === 0;
  const runway = plan?.ready_count;
  const available = all.length;
  const active = MODES.find((m) => m.id === mode);
  const secsTotal = plan?.secs_each ? plan.secs_each * topics.length : 0;
  const pickable = shown.filter((t) => !t.already_queued);
  const allShownPicked = pickable.length > 0 && pickable.every((t) => selected.has(t.key));
  const toggle = (key) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(key)) n.delete(key); else n.add(key);
    return n;
  });
  const toggleShown = () => setSelected((s) => {
    const n = new Set(s);
    for (const t of pickable) { if (allShownPicked) n.delete(t.key); else n.add(t.key); }
    return n;
  });

  // Only never-rendered topics add to what is ready to post; re-rendering an
  // existing video replaces a local file and adds nothing new.
  const adds = topics.filter((t) => !t.uploaded && !t.exported).length;
  const blocked = topics.filter((t) => !t.playlist_exists);
  const live = topics.filter((t) => t.uploaded);
  const longOnes = topics.filter((t) => (t.duration_sec ?? 0) > 30);

  const start = async () => {
    const ok = await confirm({
      title: `Render ${plural(topics.length, "video")}?`,
      message: `This runs every step for each video${secsTotal ? `, roughly ${fmtMins(secsTotal)} in all` : ""}.`,
      items: topics.map((t) => ({
        title: t.title || t.key,
        meta: `${t.playlist}${t.last_rendered ? ` · last made ${t.last_rendered}` : " · never rendered"}`,
      })),
      detail: live.length
        ? `${live.length} of these ${live.length === 1 ? "is" : "are"} already published on YouTube. Re-rendering replaces your local copy only.`
        : (refresh ? "Source data will be downloaded again instead of using the saved copy." : undefined),
      confirmLabel: "Start rendering",
      cancelLabel: "Not now",
      tone: live.length ? "danger" : "primary",
    });
    if (!ok) return;
    await onRenderBatch({
      keys: topics.map((t) => t.key),
      refresh,
      label: active.label.toLowerCase(),
    });
    setSelected(new Set());
    loadPlan();
  };

  const playlistOptions = [
    { value: "", label: "All playlists" },
    ...series.map((s) => {
      const n = all.filter((t) => t.series === s.series).length;
      return { value: s.series, label: s.playlist + (n ? ` (${n})` : "") };
    }),
  ];

  return (
    <>
      <PageHeader title="Shorts" sub="Render daily Shorts and the Shorts cut from your videos. They share one queue." />

      <div className="split">
        <div className="wide stack" style={{ gap: 18 }}>
          <LiveRun job={job} queue={queue} lines={lines} titles={titles}
                   onCancel={onCancel} onCancelQueued={onCancelQueued} />

          <FromVideos job={job} queue={queue}
                      onRender={(keys, label) => onRenderBatch({ keys, refresh: false, label })} />

          <section className="card" aria-label="Step 1: what kind of work">
            <div className="card-head"><Chip plain tone="go" className="num">1</Chip><h2>What kind of work?</h2></div>
            <div className="cols c3">
              {MODES.map((m) => (
                <button key={m.id} type="button" aria-pressed={mode === m.id}
                        className={"card lift pick" + (m.id === "recut" ? " risky" : "")}
                        onClick={() => setMode(m.id)}>
                  <div className="rowf" style={{ justifyContent: "space-between" }}>
                    <b>{m.label}</b>
                    <span className="num" style={{ fontSize: 20 }}>{plan?.counts?.[m.id] ?? ""}</span>
                  </div>
                  <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>{m.blurb}</p>
                </button>
              ))}
            </div>
          </section>

          <section className="card" aria-label="Step 2: pick videos" aria-busy={loading}>
            <div className="card-head" style={{ flexWrap: "wrap" }}>
              <Chip plain tone="go" className="num">2</Chip>
              <h2>Pick the videos to render</h2>
              {plan && (
                <span className="muted" style={{ fontSize: 13 }}>
                  {topics.length} of {plural(available, "video")} ticked
                </span>
              )}
            </div>
            <div className="rowf" style={{ gap: 14, alignItems: "flex-end", marginBottom: 12 }}>
              <Search value={q} onChange={setQ} placeholder="Search title or key" label="Search videos" />
              <label className="field">
                Playlist
                <Select value={pickedSeries} onChange={setPickedSeries} options={playlistOptions} />
              </label>
              <label className="rowf" style={{ minHeight: 44 }}>
                <input className="check" type="checkbox" checked={refresh}
                       onChange={(e) => setRefresh(e.target.checked)} />
                <span>
                  Pull fresh source data
                  <span className="faint" style={{ fontSize: 12.5 }}> · skips the saved copy</span>
                </span>
              </label>
            </div>
            {firstLoad && <SkeletonRows rows={3} />}
            {!firstLoad && shown.length === 0 && (
              <Empty icon="play" title="Nothing here">
                {all.length ? "No videos match this search or playlist." : active.empty}
              </Empty>
            )}
            {shown.length > 0 && (
              <>
                <div className="scroll">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th style={{ width: 36 }}>
                          <input className="check" type="checkbox" checked={allShownPicked}
                                 disabled={!pickable.length} onChange={toggleShown}
                                 aria-label="Tick every video in this list" />
                        </th>
                        <th>Video</th><th>Playlist</th><th>Chart</th>
                        <th>Status</th><th>Last made</th>
                        <th style={{ width: 48 }}><span className="sr">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {paged.slice.map((t) => (
                        <PlanRow key={t.key} t={t} checked={selected.has(t.key)}
                                 onToggle={() => toggle(t.key)}
                                 onRevert={async () => { await onRevertTopic(t.key, t.title); loadPlan(); }} />
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="rowf" style={{ justifyContent: "space-between", marginTop: 10 }}>
                  <Pager p={paged} noun="videos" />
                  {selected.size > 0 && (
                    <button type="button" className="link" style={{ fontSize: 13 }}
                            onClick={() => setSelected(new Set())}>
                      Clear {plural(topics.length, "tick")}
                    </button>
                  )}
                </div>
              </>
            )}
          </section>
        </div>

        <aside className="rail" aria-label="Start the batch" style={{ position: "sticky", top: 24 }}>
          <section className="card" style={{ borderColor: "rgba(200,245,96,.4)" }}>
            <div className="card-head"><h2>Ready to start</h2></div>
            <div className="cols" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div className="stat">
                <div className="lbl">Videos</div>
                <div className="val" style={{ fontSize: 24 }}>{topics.length}</div>
              </div>
              {secsTotal > 0 && (
                <div className="stat">
                  <div className="lbl">Time</div>
                  <div className="val" style={{ fontSize: 24 }}>{fmtMins(secsTotal)}</div>
                  <div className="note">{fmtMins(plan.secs_each)} each, from recent jobs</div>
                </div>
              )}
            </div>

            <Btn kind="primary" icon={nothing ? undefined : "play"} style={{ width: "100%", marginTop: 16 }}
                 disabled={nothing || busy} onClick={start}>
              {nothing ? "Tick videos to render" : `Start ${plural(topics.length, "render")}`}
            </Btn>
            <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>
              {busy
                ? "A render is running. You can start the next batch when it finishes."
                : "Each video becomes its own job, one after another."}
            </p>
          </section>

          {live.length > 0 && (
            <Banner tone="warn" title={`${plural(live.length, "video")} already published`}>
              Re-rendering replaces your local copy only. The live video stays as it is until you
              upload the new file yourself.
            </Banner>
          )}
          {blocked.length > 0 && (
            <Banner tone="warn" title="Playlist not on YouTube yet">
              {[...new Set(blocked.map((t) => t.playlist))].join(", ")}: create the playlist before
              you post these.
            </Banner>
          )}
          {longOnes.length > 0 && (
            <Banner tone="info" title={`${plural(longOnes.length, "current cut")} longer than 30s`}>
              That is where viewers tend to drop off. Re-rendering will not shorten them on its own.
            </Banner>
          )}
          {mode !== "recut" && runway >= 10 && (
            <Banner tone="info" title={`${runway} videos are already ready to post`}>
              That covers about {runway} days of daily uploads. Rendering more is optional.
            </Banner>
          )}

          {plan && (
            <section className="card">
              <div className="card-head"><h2>After this batch</h2></div>
              <div className="stack" style={{ fontSize: 13.5 }}>
                <div className="rowf" style={{ justifyContent: "space-between" }}>
                  <span className="muted">Ready to post</span>
                  <span className="num">{runway} → {runway + adds}</span>
                </div>
                <div className="rowf" style={{ justifyContent: "space-between" }}>
                  <span className="muted">Days of posting covered</span>
                  <span className="num">{runway} → {runway + adds}</span>
                </div>
                <div className="rowf" style={{ justifyContent: "space-between" }}>
                  <span className="muted">{mode === "new" ? "Left to render" : "Left in this group"}</span>
                  <span className="num">{available} → {Math.max(0, available - topics.length)}</span>
                </div>
              </div>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
