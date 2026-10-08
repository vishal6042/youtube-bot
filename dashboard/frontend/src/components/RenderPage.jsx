import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Btn, Chip, Empty, MODE_LABEL, PageHeader, PlaylistChip, Select, SkeletonRows, Thumb,
  fmtDuration,
} from "../ui.jsx";
import LiveRun from "./LiveRun.jsx";
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

const COUNTS = [1, 2, 3, 5, 7, 10];

function fmtMins(secs) {
  if (!secs) return "";
  const m = Math.round(secs / 60);
  return m < 1 ? "under 1 min" : `~${m} min`;
}

function daysAgo(iso) {
  if (!iso) return null;
  const d = Math.round((Date.now() - new Date(iso + "T00:00:00").getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function PlanRow({ t, n, onRemove, onRevert }) {
  const last = t.last_rendered ? `${daysAgo(t.last_rendered)}` : "Never";
  const more = [
    t.episode != null && `Episode ${t.episode}`,
    t.mood && `${t.mood} music`,
    [t.source, t.fetcher].filter(Boolean).join(" · "),
  ].filter(Boolean).join("\n");

  return (
    <tr title={more}>
      <td className="num faint">{n}</td>
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
        {last}{t.duration_sec != null ? ` · ${fmtDuration(t.duration_sec)}` : ""}
      </td>
      <td>
        <div className="rowf" style={{ gap: 0, flexWrap: "nowrap", justifyContent: "flex-end" }}>
          {t.staged_new && !t.already_queued && (
            <Btn kind="ghost" size="sm" icon="trash"
                 iconOnly={`Delete ${t.title || t.key} from the topic list (never rendered)`}
                 onClick={onRevert} />
          )}
          <Btn kind="ghost" size="sm" icon="close"
               iconOnly={`Remove ${t.title || t.key} from this plan`} onClick={onRemove} />
        </div>
      </td>
    </tr>
  );
}

export default function RenderPage({ series = [], job, queue = [], lines, onRenderBatch, onRevertTopic,
                                     onCancel, onCancelQueued, confirm, busy, pipelineVersion }) {
  const [mode, setMode] = useState("new");
  const [count, setCount] = useState(3);
  const [pickedSeries, setPickedSeries] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [autoPicked, setAutoPicked] = useState(false);
  const [removed, setRemoved] = useState(() => new Set());
  const reqRef = useRef(0);

  const loadPlan = useCallback(async () => {
    const req = ++reqRef.current;
    setLoading(true);
    try {
      const q = new URLSearchParams({ batch: String(count), mode });
      if (pickedSeries) q.set("series", pickedSeries);
      const p = await api(`/api/plan?${q}`);
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
  }, [count, mode, pickedSeries, autoPicked, pipelineVersion]);

  useEffect(() => { loadPlan(); }, [loadPlan]);
  // A different question gets a fresh plan; hand-removed rows do not carry over.
  useEffect(() => { setRemoved(new Set()); }, [count, mode, pickedSeries]);

  const titles = useMemo(() => {
    const map = {};
    for (const s of series) for (const i of s.items || []) if (i.title) map[i.key] = i.title;
    for (const t of plan?.topics || []) if (t.title) map[t.key] = t.title;
    return map;
  }, [series, plan]);

  const topics = (plan?.topics || []).filter((t) => !removed.has(t.key));
  const firstLoad = loading && !plan;
  const nothing = !firstLoad && topics.length === 0;
  const runway = plan?.ready_count;
  const available = plan?.available ?? 0;
  const active = MODES.find((m) => m.id === mode);
  const secsTotal = plan?.secs_each ? plan.secs_each * topics.length : 0;

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
    setRemoved(new Set());
    loadPlan();
  };

  const playlistOptions = [
    { value: "", label: "All playlists" },
    ...series.map((s) => {
      const n = plan?.available_by_playlist?.[s.playlist];
      return { value: s.series, label: s.playlist + (n ? ` (${n})` : "") };
    }),
  ];

  return (
    <>
      <PageHeader title="Render" sub="Choose what to build, see exactly what will run, then start it" />

      <div className="split">
        <div className="wide stack" style={{ gap: 18 }}>
          <LiveRun job={job} queue={queue} lines={lines} titles={titles}
                   onCancel={onCancel} onCancelQueued={onCancelQueued} />

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

          <section className="card" aria-label="Step 2: how many and from where">
            <div className="card-head" style={{ flexWrap: "wrap" }}>
              <Chip plain tone="go" className="num">2</Chip>
              <h2>How many, and from which playlist?</h2>
              {plan && (
                <span className="muted" style={{ fontSize: 13 }}>
                  {plural(available, "topic")} {available === 1 ? "matches" : "match"}
                  {pickedSeries ? " in this playlist" : ""}
                </span>
              )}
            </div>
            <div className="rowf" style={{ gap: 18, alignItems: "flex-end" }}>
              <div className="field">
                <span id="render-count">How many</span>
                <div className="seg" role="group" aria-labelledby="render-count">
                  {COUNTS.map((n) => (
                    <button key={n} type="button" className={count === n ? "on" : ""}
                            aria-pressed={count === n}
                            disabled={n > available && available > 0}
                            style={n > available && available > 0 ? { opacity: .4, cursor: "not-allowed" } : undefined}
                            onClick={() => setCount(n)}>
                      {n}
                    </button>
                  ))}
                </div>
              </div>
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
          </section>

          <section className="card" aria-label="Step 3: the plan" aria-busy={loading}>
            <div className="card-head" style={{ flexWrap: "wrap" }}>
              <Chip plain tone="go" className="num">3</Chip>
              <h2>The plan</h2>
              <span className="muted" style={{ fontSize: 13 }}>
                exactly what will run, in this order · remove any you don't want
              </span>
            </div>
            {firstLoad && <SkeletonRows rows={3} />}
            {nothing && (
              <Empty icon="play" title="Nothing to render">
                {removed.size > 0 && plan?.topics?.length
                  ? "You removed every topic from this plan."
                  : plan ? active.empty : "The plan could not be loaded."}
              </Empty>
            )}
            {nothing && removed.size > 0 && (
              <div style={{ textAlign: "center" }}>
                <Btn size="sm" icon="undo" onClick={() => setRemoved(new Set())}>Put them back</Btn>
              </div>
            )}
            {topics.length > 0 && (
              <div className="scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 36 }}>#</th><th>Video</th><th>Playlist</th><th>Chart</th>
                      <th>Status</th><th>Last made</th>
                      <th style={{ width: 90 }}><span className="sr">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {topics.map((t, i) => (
                      <PlanRow key={t.key} t={t} n={i + 1}
                               onRemove={() => setRemoved((s) => new Set(s).add(t.key))}
                               onRevert={async () => { await onRevertTopic(t.key, t.title); loadPlan(); }} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!nothing && removed.size > 0 && (
              <button type="button" className="link" style={{ fontSize: 13, marginTop: 10 }}
                      onClick={() => setRemoved(new Set())}>
                Put back {plural(removed.size, "removed topic")}
              </button>
            )}

          </section>
        </div>

        <aside className="rail" aria-label="Start the batch" style={{ position: "sticky", top: 24 }}>
          <section className="card" style={{ borderColor: "rgba(200,245,96,.4)" }}>
            <div className="card-head"><h2>Ready to start</h2></div>
            <div className="cols" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div className="stat">
                <div className="lbl">Videos</div>
                <div className="val" style={{ fontSize: 24 }}>{firstLoad ? "" : topics.length}</div>
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
                 disabled={nothing || firstLoad || busy} onClick={start}>
              {nothing || firstLoad ? "Nothing to render" : `Start ${plural(topics.length, "render")}`}
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
