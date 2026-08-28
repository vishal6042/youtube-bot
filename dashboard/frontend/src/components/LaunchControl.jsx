import { useCallback, useEffect, useState } from "react";
import Chip from "./Chip.jsx";
import PlaylistCover from "./PlaylistCover.jsx";
import { api, seriesChip } from "../api.js";

/* Full-screen Launch Control. Strategies are intents, not orderings: "re-cut"
   deliberately targets videos that are already public, so it is opt-in and
   clearly labelled everywhere it appears. */
const MODES = [
  { id: "new", label: "NEW TOPICS", icon: "✨",
    blurb: "Topics that have never been rendered — genuinely new content.",
    hint: "Safest choice: nothing exists yet, so nothing can be overwritten." },
  { id: "staged", label: "IMPROVE STAGED", icon: "♻",
    blurb: "Re-render videos that are staged but not yet uploaded.",
    hint: "Fresher numbers land before you post. The old local copy is replaced." },
  { id: "recut", label: "RE-CUT PUBLISHED", icon: "⚠",
    blurb: "Videos already live on YouTube, oldest render first.",
    hint: "Only for refreshing published videos. The live video is untouched until you re-upload." },
];

const COUNTS = [1, 2, 3, 5, 7, 10];

/* Chart modes vary now, so name them rather than showing a raw config value. */
const MODE_NAMES = {
  bar_race: "Bar race",
  line_grow: "Growing line",
  bump_race: "Bump / rank race",
  waffle_grow: "Waffle grid",
  scene: "Narrated scene",
};

function fmtMins(secs) {
  if (!secs) return "—";
  const m = Math.round(secs / 60);
  return m < 1 ? "under a minute" : m === 1 ? "~1 min" : `~${m} min`;
}

function fmtDur(secs) {
  if (secs == null) return null;
  return secs >= 60 ? `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s` : `${Math.round(secs)}s`;
}

function daysAgo(iso) {
  if (!iso) return null;
  const d = Math.round((Date.now() - new Date(iso + "T00:00:00").getTime()) / 86400000);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
}

export default function LaunchControl({ series, onRenderBatch, onRevertTopic, onBack,
                                        onStarted, confirm, busy, pipelineVersion }) {
  const [mode, setMode] = useState("new");
  const [count, setCount] = useState(3);
  const [pickedSeries, setPickedSeries] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [autoPicked, setAutoPicked] = useState(false);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams({ batch: String(count), mode });
      if (pickedSeries) q.set("series", pickedSeries);
      const p = await api(`/api/plan?${q}`);
      // First load only: if there is no genuinely new work, fall back to the
      // next most useful strategy rather than showing an empty screen.
      if (!autoPicked && mode === "new" && p.counts?.new === 0) {
        setAutoPicked(true);
        setMode(p.counts.staged > 0 ? "staged" : "recut");
        return;
      }
      setAutoPicked(true);
      setPlan(p);
    } catch {
      setPlan(null);
    }
    setLoading(false);
    // pipelineVersion changes whenever a job starts/finishes, so a completed
    // render drops out of the preview instead of lingering greyed-out.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count, mode, pickedSeries, autoPicked, pipelineVersion]);

  useEffect(() => { loadPlan(); }, [loadPlan]);

  const topics = plan?.topics || [];
  const nothing = !loading && topics.length === 0;
  const runway = plan?.ready_count ?? 0;
  const available = plan?.available ?? 0;
  const active = MODES.find((m) => m.id === mode);

  // What this launch does to the queue. Only never-uploaded renders add runway;
  // re-cutting a published video replaces a local file and stages nothing new.
  const adds = topics.filter((t) => !t.uploaded && !t.exported).length;
  const blocked = topics.filter((t) => !t.playlist_exists);
  const live = topics.filter((t) => t.uploaded);
  const longOnes = topics.filter((t) => (t.duration_sec ?? 0) > 30);

  const launch = async () => {
    const ok = await confirm({
      title: `Render ${topics.length} video${topics.length === 1 ? "" : "s"}?`,
      message: `This runs the full pipeline for each topic — roughly ${fmtMins(plan?.secs_total)}.`,
      items: topics.map((t) => ({
        title: t.title,
        meta: `${t.playlist}${t.last_rendered ? ` · last made ${t.last_rendered}` : " · never rendered"}`,
      })),
      detail: live.length
        ? `⚠ ${live.length} of these are already published on YouTube. Re-rendering replaces your local copy only.`
        : (refresh ? "Source data will be re-fetched, ignoring the cache." : undefined),
      confirmLabel: "▶ START RENDERING",
      tone: live.length ? "danger" : "primary",
    });
    if (!ok) return;
    await onRenderBatch({
      keys: topics.map((t) => t.key),
      refresh,
      label: `${count} × ${mode === "new" ? "new" : "rotate"}`,
    });
    loadPlan();
    // Renders report progress on Mission, so follow the work there.
    if (onStarted) onStarted();
  };

  return (
    <div className="lcp">
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">LAUNCH CONTROL</div>
            <div className="pl-series">
              plan a render batch, see exactly what will run, then launch it
            </div>
          </div>
          <div className={"lcp-runway " + (runway >= 10 ? "ok" : runway >= 4 ? "warn" : "low")}>
            <b>{runway}</b>
            <span>ready to upload · ≈{runway} days of runway</span>
          </div>
        </div>
      </section>

      {/* ---- 1. strategy ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">1</span>
          <span className="panel-title">STRATEGY</span>
          <span className="lcp-step-hint">What kind of work do you want to do?</span>
        </div>
        <div className="lcp-modes">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={"lcp-mode" + (mode === m.id ? " active" : "") +
                         (m.id === "recut" ? " danger" : "")}
              onClick={() => setMode(m.id)}
            >
              <span className="lcp-mode-top">
                <span className="lcp-mode-icon">{m.icon}</span>
                <span className="lcp-mode-label">{m.label}</span>
                <span className="lcp-mode-count">{plan?.counts?.[m.id] ?? 0}</span>
              </span>
              <span className="lcp-mode-blurb">{m.blurb}</span>
            </button>
          ))}
        </div>
        <p className="lcp-mode-hint">{active.hint}</p>
      </section>

      {/* ---- 2. scope ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">2</span>
          <span className="panel-title">SCOPE</span>
          <span className="lcp-step-hint">
            {available} topic{available === 1 ? "" : "s"} match this strategy
            {pickedSeries ? " in this playlist" : ""}.
          </span>
        </div>
        <div className="lcp-scope">
          <div className="lc-field">
            <span className="set-label">HOW MANY</span>
            <div className="lc-chips">
              {COUNTS.map((n) => (
                <button
                  key={n}
                  className={"fchip fchip-sm" + (count === n ? " active" : "")}
                  disabled={n > available && available > 0}
                  onClick={() => setCount(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="lc-field">
            <span className="set-label">PLAYLIST</span>
            <select value={pickedSeries} onChange={(e) => setPickedSeries(e.target.value)}>
              <option value="">All playlists</option>
              {series.map((s) => {
                const n = plan?.available_by_playlist?.[s.playlist];
                return (
                  <option key={s.series} value={s.series}>
                    {s.playlist}{n ? ` (${n})` : ""}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="lc-field">
            <span className="set-label">SOURCE DATA</span>
            <label className="lc-check">
              <input type="checkbox" checked={refresh}
                     onChange={(e) => setRefresh(e.target.checked)} />
              <span>
                Re-fetch source data
                <span className="lc-hint"> — ignore the cache and pull fresh numbers</span>
              </span>
            </label>
          </div>
        </div>
      </section>

      {/* ---- 3. the plan ---- */}
      <section className="panel lcp-step">
        <div className="lcp-step-head">
          <span className="lcp-num">3</span>
          <span className="panel-title">RENDER PLAN</span>
          <span className="lcp-step-hint">
            {topics.length} topic{topics.length === 1 ? "" : "s"} ·{" "}
            {fmtMins(plan?.secs_total)} total · {fmtMins(plan?.secs_each)} each
          </span>
        </div>

        <div className="lcp-plan">
          {loading && <div className="empty">Planning…</div>}
          {nothing && (
            <div className="empty">
              {mode === "new"
                ? "Nothing new to render. Pick suggestions in Build Next and they appear here."
                : mode === "staged"
                  ? "Nothing is staged awaiting upload."
                  : "No topics match these options."}
            </div>
          )}
          {!loading && topics.map((t, i) => (
            <div key={t.key} className={"lcp-row" + (t.already_queued ? " dim" : "")}>
              <span className="lcp-row-num">{String(i + 1).padStart(2, "0")}</span>
              <span className="lcp-row-art">
                {t.has_thumb
                  ? <img src={`/api/thumb/${t.key}`} alt="" loading="lazy" />
                  : <PlaylistCover series={t.series} />}
              </span>
              <span className="lcp-row-main">
                <span className="lcp-row-title">{t.title}</span>
                {t.subtitle && <span className="lcp-row-sub">{t.subtitle}</span>}
                <span className="lcp-row-facts">
                  <Chip cls={seriesChip(t.series)}>{t.playlist}</Chip>
                  <span className="lcp-fact">EP {t.episode}</span>
                  {t.chart_mode && (
                    <span className="lcp-fact">
                      {MODE_NAMES[t.chart_mode] || t.chart_mode}
                    </span>
                  )}
                  {t.narrated && <span className="lcp-fact">narrated</span>}
                  {t.mood && <span className="lcp-fact">♪ {t.mood}</span>}
                </span>
                <span className="lcp-row-src">
                  {t.source}
                  {t.fetcher && <span className="pd-dot">·</span>}
                  {t.fetcher}
                </span>
              </span>
              <span className="lcp-row-state">
                <span className="lcp-when">
                  {t.last_rendered
                    ? <>last made {t.last_rendered}<em>· {daysAgo(t.last_rendered)}</em></>
                    : <>never rendered</>}
                </span>
                {t.duration_sec != null && (
                  <span className={"lcp-len" + (t.duration_sec > 30 ? " warn" : "")}>
                    current cut {fmtDur(t.duration_sec)}
                  </span>
                )}
              </span>
              <span className="lcp-row-side">
                {t.already_queued && <span className="chip chip-pending">in queue</span>}
                {!t.already_queued && t.uploaded && (
                  <span className="chip chip-failed"
                        title="Already public on YouTube. Re-rendering replaces your local copy only.">
                    ⚠ already live
                  </span>
                )}
                {!t.already_queued && !t.uploaded && t.exported && (
                  <span className="chip chip-ready" title="Staged for upload but not posted yet">
                    staged
                  </span>
                )}
                {!t.playlist_exists && (
                  <span className="chip chip-failed" title="This playlist does not exist on YouTube yet">
                    ⚠ no playlist
                  </span>
                )}
                {t.staged_new && !t.already_queued && (
                  <>
                    <span className="chip chip-queue">new</span>
                    <button
                      className="btn btn-mini lc-revert"
                      title="Remove this topic from the catalog again"
                      onClick={async () => { await onRevertTopic(t.key, t.title); loadPlan(); }}
                    >✕ REVERT</button>
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ---- 4. impact + launch ---- */}
      <section className="panel lcp-step lcp-final">
        <div className="lcp-step-head">
          <span className="lcp-num">4</span>
          <span className="panel-title">IMPACT</span>
          <span className="lcp-step-hint">What this launch changes.</span>
        </div>

        <div className="lcp-impact">
          <div className="lcp-imp">
            <span>Runway after</span>
            <b>{runway} → {runway + adds}</b>
            <em>{adds ? `+${adds} newly staged` : "no new videos staged"}</em>
          </div>
          <div className="lcp-imp">
            <span>Time to run</span>
            <b>{fmtMins(plan?.secs_total)}</b>
            <em>{fmtMins(plan?.secs_each)} per video, measured from recent jobs</em>
          </div>
          <div className="lcp-imp">
            <span>Left after this</span>
            <b>{Math.max(0, available - topics.length)}</b>
            <em>more topics match this strategy</em>
          </div>
        </div>

        {(live.length > 0 || blocked.length > 0 || longOnes.length > 0) && (
          <div className="lcp-warns">
            {live.length > 0 && (
              <div className="lc-note lc-note-warn">
                ⚠ {live.length} of these {live.length === 1 ? "is" : "are"} already published on
                YouTube. Re-rendering replaces your local copy only — the live video stays as it
                is until you re-upload it yourself.
              </div>
            )}
            {blocked.length > 0 && (
              <div className="lc-note lc-note-warn">
                ⚠ {blocked.map((t) => t.playlist).join(", ")} {blocked.length === 1 ? "does" : "do"}
                {" "}not exist on YouTube yet — create the playlist before you post these.
              </div>
            )}
            {longOnes.length > 0 && (
              <div className="lc-note">
                {longOnes.length} current cut{longOnes.length === 1 ? "" : "s"} run past 30s, where
                your retention drops off. Re-rendering will not shorten them on its own.
              </div>
            )}
          </div>
        )}

        {mode !== "recut" && runway >= 10 && (
          <div className="lc-note">
            You already have {runway} videos staged — about {runway} days of daily uploads.
            Rendering more is optional.
          </div>
        )}

        <button
          className="btn btn-primary lcp-launch"
          disabled={nothing || loading || busy}
          onClick={launch}
        >
          {nothing
            ? "NOTHING TO RENDER"
            : `▶ LAUNCH ${topics.length} RENDER${topics.length === 1 ? "" : "S"}`}
        </button>
      </section>
    </div>
  );
}
