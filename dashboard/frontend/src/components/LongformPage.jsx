import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Bar, Btn, Chip, Empty, Icon, PageHeader, Pager, PlaylistChip, Select, SkeletonRows, Stat,
  usePaged,
} from "../ui.jsx";
import LongformLive from "./LongformLive.jsx";
import "../screens/longform.css";

const WPM = 150;
const clock = (secs) => {
  const s = Math.max(0, Math.round(secs || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const wordCount = (text) => (text || "").trim().split(/\s+/).filter(Boolean).length;
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;

const MODES = [
  { value: "line_multi", label: "Head to head" },
  { value: "bar_race", label: "Bar race" },
  { value: "bump_race", label: "Rank race" },
  { value: "line_grow", label: "Single line" },
];
const MOODS = ["majestic", "reflective", "hopeful", "calm", "serene", "lofi"];
const PACES = [
  { value: "+0%", label: "Normal pace" }, { value: "+5%", label: "Slightly faster" },
  { value: "+10%", label: "Faster" }, { value: "+15%", label: "Brisk" },
];

function statusOf(ep) {
  if (ep.build?.live) return ["Rendering", "go"];
  if (ep.has_video && !ep.video_stale) return ["Rendered", "go"];
  if (ep.has_video) return ["Edited since last render", "warn"];
  if (ep.reviewed) return ["Script reviewed", "info"];
  return ["Script draft", "info"];
}

function Steps({ ep }) {
  const n = ep.chapters.length;
  const assembled = ep.has_video && !ep.video_stale;
  const steps = [
    ["Script", ep.reviewed, ep.reviewed ? "reviewed" : n ? "draft, needs review" : "not started"],
    ["Voice and charts", n > 0 && ep.rendered === n, `${ep.rendered} of ${n} chapters rendered`],
    ["Assembled", assembled, assembled ? clock(ep.build?.secs || ep.secs) : ep.has_video ? "out of date" : "not yet"],
    ["Published", false, "not yet"],
  ];
  const now = steps.findIndex(([, done]) => !done);
  return (
    <ol className="lf-steps" aria-label="Progress">
      {steps.map(([name, done, note], i) => (
        <li key={name} className={done ? "done" : i === now ? "now" : ""}><b>{name}</b>{note}</li>
      ))}
    </ol>
  );
}

function Player({ src, title, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-back" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal lf-player" role="dialog" aria-modal="true" aria-label={title}>
        <div className="rowf" style={{ flexWrap: "nowrap", marginBottom: 12 }}>
          <b style={{ flex: 1, minWidth: 0 }}>{title}</b>
          <Btn kind="ghost" size="sm" icon="close" iconOnly="Close" onClick={onClose} />
        </div>
        <video src={src} controls autoPlay playsInline />
      </div>
    </div>
  );
}

/* ───────────────────────────── episode list ───────────────────────────── */

function EpisodeList({ data, onOpen, onCreate, onWatch }) {
  const ideas = usePaged(data.ideas, 5);
  const inProgress = data.episodes.filter((e) => !(e.has_video && !e.video_stale)).length;
  return (
    <>
      <PageHeader title="Long-form"
                  sub="Narrated videos of around 5 to 10 minutes, built from chart chapters and a written script">
        <Btn kind="primary" icon="plus" onClick={() => onCreate()}>New episode</Btn>
      </PageHeader>

      <section className="cols c4" aria-label="Long-form totals">
        <Stat label="Episodes" value={data.episodes.length} note={`${inProgress} still in progress`} />
        <Stat label="Rendered" value={data.episodes.length - inProgress} note="ready to watch" />
        <Stat label="Rendering now" value={data.building ? 1 : 0} note={data.building || "nothing running"} />
        <Stat label="Ideas waiting" value={data.ideas.length} note="from the long-form plan" />
      </section>

      {data.episodes.length === 0 && (
        <div className="card">
          <Empty icon="screen" title="No episodes yet"
                 action={<Btn kind="primary" onClick={() => onCreate()}>New episode</Btn>}>
            Start one from an idea below, or from a blank script.
          </Empty>
        </div>
      )}

      {data.episodes.filter((e) => e.build?.live).map((e) => (
        <LongformLive key={e.key} ep={e} onOpen={() => onOpen(e.key)} />
      ))}

      {data.episodes.map((ep) => {
        const [label, tone] = statusOf(ep);
        return (
          <section key={ep.key} className="card" aria-label={ep.title}
                   style={{ borderColor: ep.build?.live ? "rgba(200,245,96,.4)" : undefined }}>
            <div className="split" style={{ alignItems: "center" }}>
              <div style={{ flex: "0 1 300px", minWidth: 220 }}>
                {ep.has_video ? (
                  <button type="button" className="lf-wide" onClick={() => onWatch(ep)}
                          aria-label={`Watch ${ep.title}`}>
                    <Icon name="play" size={34} />
                  </button>
                ) : (
                  <div className="lf-wide"><span style={{ fontSize: 13 }}>Not rendered yet</span></div>
                )}
              </div>
              <div className="wide stack" style={{ gap: 14 }}>
                <div className="rowf">
                  <PlaylistChip series={ep.series} name={ep.playlist} />
                  <Chip tone={tone}>{label}</Chip>
                  {ep.checks > 0 && !ep.reviewed && (
                    <Chip tone="warn" plain>{plural(ep.checks, "line")} to fact-check</Chip>
                  )}
                </div>
                <div>
                  <h2 style={{ fontSize: 22, letterSpacing: "-.02em" }}>{ep.title}</h2>
                  <div className="muted" style={{ fontSize: 13.5, marginTop: 4 }}>
                    {plural(ep.chapters.length, "chapter")} · {ep.words} words · about {clock(ep.secs)}
                    {ep.target_minutes ? ` · target ${ep.target_minutes} minutes` : ""}
                  </div>
                </div>
                <Steps ep={ep} />
                <div className="rowf">
                  <Btn kind="primary" onClick={() => onOpen(ep.key)}>Open the editor</Btn>
                  {ep.has_video && <Btn icon="play" onClick={() => onWatch(ep)}>Watch</Btn>}
                </div>
              </div>
            </div>
          </section>
        );
      })}

      {data.ideas.length > 0 && (
        <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Ideas for the next episodes">
          <div className="rowf" style={{ padding: "12px 12px 6px" }}>
            <h2>Next episodes</h2>
            <span className="muted" style={{ fontSize: 13 }}>each one reuses data the channel already charts</span>
          </div>
          <div className="scroll">
            <table className="tbl">
              <thead><tr><th>Episode idea</th><th>Playlist</th><th>Chapters would use</th>
                <th style={{ width: 150 }}><span className="sr">Actions</span></th></tr></thead>
              <tbody>
                {ideas.slice.map((i) => (
                  <tr key={i.title}>
                    <td className="t">{i.title}</td>
                    <td><PlaylistChip series={i.series} name={i.playlist} /></td>
                    <td className="muted">{i.uses}</td>
                    <td><Btn size="sm" onClick={() => onCreate(i)}>Start script</Btn></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager p={ideas} noun="ideas" sizes={null} style={{ padding: "14px 12px 0" }} />
        </section>
      )}
    </>
  );
}

/* ───────────────────────────── episode editor ───────────────────────────── */

function Figures({ epKey, chapterId, version }) {
  const [res, setRes] = useState(null);
  useEffect(() => {
    let live = true;
    setRes(null);
    api(`/api/longform/${epKey}/chapter/${chapterId}/figures`)
      .then((r) => live && setRes(r))
      .catch((e) => live && setRes({ ok: false, error: e.message, figures: [] }));
    return () => { live = false; };
  }, [epKey, chapterId, version]);

  return (
    <div className="card" style={{ background: "var(--bg)", padding: "14px 16px" }}>
      <div className="rowf" style={{ marginBottom: 8 }}>
        <b>Figures from the data for this chart</b>
        {res?.ok && <span className="faint" style={{ fontSize: 12.5 }}>{res.source} · {res.years?.join("–")}</span>}
      </div>
      {!res && <div className="skel" style={{ height: 16, width: "70%" }} />}
      {res && !res.ok && <p style={{ color: "var(--bad)", fontSize: 13.5 }}>{res.error}</p>}
      {res?.ok && (
        <ul className="stack" style={{ margin: 0, padding: 0, listStyle: "none", gap: 6, fontSize: 13.5 }}>
          {res.figures.map((f) => <li key={f} className="rowf" style={{ flexWrap: "nowrap", alignItems: "baseline" }}>
            <span className="dot" style={{ alignSelf: "center" }} /><span className="num">{f}</span></li>)}
        </ul>
      )}
      <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>
        Check the numbers in the narration against these. They update when the chart is saved.
      </p>
    </div>
  );
}

function Editor({ epKey, meta, onBack, toast, confirm, onOpen }) {
  const [saved, setSaved] = useState(null);   // last copy from the server
  const [ep, setEp] = useState(null);         // working copy
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [watch, setWatch] = useState(null);
  const [audio, setAudio] = useState(null);
  const timer = useRef(null);

  const load = useCallback(async (adopt) => {
    try {
      const s = await api(`/api/longform/${epKey}`);
      setSaved(s);
      if (adopt) setEp(s);
      return s;
    } catch (e) {
      toast(e.message, true);
      return null;
    }
  }, [epKey, toast]);

  useEffect(() => { load(true); }, [load]);

  // While a render runs, keep its progress fresh without touching the draft.
  const live = saved?.build?.live;
  useEffect(() => {
    if (!live) return undefined;
    timer.current = setInterval(() => load(false), 3000);
    return () => clearInterval(timer.current);
  }, [live, load]);

  const dirty = useMemo(() => {
    if (!ep || !saved) return false;
    const pick = (e) => JSON.stringify([e.title, e.voice, e.voice_rate, e.music_mood, e.target_minutes,
      e.reviewed, e.chapters.map((c) => [c.id, c.heading, c.chart, c.narration, c.check])]);
    return pick(ep) !== pick(saved);
  }, [ep, saved]);

  if (!ep) return <SkeletonRows rows={8} />;

  const chapters = ep.chapters;
  const ch = chapters[Math.min(sel, chapters.length - 1)];
  const savedCh = saved.chapters.find((c) => c.id === ch?.id);
  // Measured length when the words are unchanged since the last render;
  // otherwise an estimate from the word count.
  const secsOf = (c) => {
    const s = saved.chapters.find((x) => x.id === c.id);
    return s && s.measured && s.narration === c.narration ? s.secs : (wordCount(c.narration) / WPM) * 60;
  };
  const totalSecs = chapters.reduce((n, c) => n + secsOf(c), 0);
  const totalWords = chapters.reduce((n, c) => n + wordCount(c.narration), 0);
  const target = (Number(ep.target_minutes) || 5) * 60;
  const checks = chapters.filter((c) => c.check).length;
  const [label, tone] = statusOf({ ...saved, reviewed: ep.reviewed });

  const patch = (fields) => setEp((e) => ({ ...e, ...fields }));
  const patchCh = (fields) => setEp((e) => ({
    ...e, chapters: e.chapters.map((c, i) => (i === sel ? { ...c, ...fields } : c)),
  }));
  const patchChart = (fields) => patchCh({ chart: { ...ch.chart, ...fields } });

  const save = async (quiet) => {
    setBusy(true);
    try {
      const s = await api(`/api/longform/${epKey}`, { episode: ep });
      setSaved(s);
      setEp(s);
      if (!quiet) toast("Episode saved");
      return s;
    } catch (e) {
      toast(e.message, true);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const addChapter = () => {
    let n = chapters.length + 1;
    while (chapters.some((c) => c.id === `chapter_${n}`)) n += 1;
    setEp((e) => ({
      ...e,
      chapters: [...e.chapters, {
        id: `chapter_${n}`, heading: "New chapter", narration: "",
        chart: { mode: "line_multi", code: meta.indicators[0].code, entities: ["India", "China"],
                 year_min: 1990, year_max: 2025 },
      }],
    }));
    setSel(chapters.length);
  };

  const removeChapter = async () => {
    if (!await confirm({
      title: "Remove this chapter?", message: `"${ch.heading || ch.id}" and its narration will be removed from the script.`,
      detail: "Nothing is deleted until you save.", confirmLabel: "Remove chapter", tone: "danger",
    })) return;
    setEp((e) => ({ ...e, chapters: e.chapters.filter((_, i) => i !== sel) }));
    setSel((i) => Math.max(0, i - 1));
  };

  const move = (dir) => {
    const to = sel + dir;
    if (to < 0 || to >= chapters.length) return;
    setEp((e) => {
      const list = [...e.chapters];
      [list[sel], list[to]] = [list[to], list[sel]];
      return { ...e, chapters: list };
    });
    setSel(to);
  };

  const listen = async () => {
    if (dirty && !await save(true)) return;
    setAudio(`/api/longform/${epKey}/chapter/${ch.id}/voice?t=${Date.now()}`);
  };

  const render = async () => {
    const changed = chapters.filter((c) => {
      const s = saved.chapters.find((x) => x.id === c.id);
      return !(s && s.rendered) || dirty;
    }).length;
    if (!await confirm({
      title: "Render this episode?",
      message: `${plural(chapters.length, "chapter")}, about ${clock(totalSecs)} of video. Each chapter that changed takes roughly 3 minutes to render; unchanged ones are reused.`,
      detail: [checks > 0 && !ep.reviewed && `${plural(checks, "line")} still marked for fact-checking.`,
               !ep.reviewed && "The script is not marked as reviewed. A draft render is fine; do not publish it."]
        .filter(Boolean).join(" ") || undefined,
      confirmLabel: changed ? "Start rendering" : "Render again", cancelLabel: "Not now",
    })) return;
    if (dirty && !await save(true)) return;
    try {
      await api(`/api/longform/${epKey}/build`, { force: false });
      toast("Rendering started");
      load(false);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const stop = async () => {
    try {
      await api(`/api/longform/${epKey}/build/stop`, {});
      toast("Render stopped. Finished chapters are kept.");
      load(false);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const build = saved.build || {};
  const countries = ch
    ? ch.chart.mode === "line_grow" ? (ch.chart.entity || "") : (ch.chart.entities || []).join(", ")
    : "";
  const setCountries = (text) => {
    const list = text.split(",").map((s) => s.trim()).filter(Boolean);
    if (ch.chart.mode === "line_grow") patchChart({ entity: list[0] || "" });
    else patchChart({ entities: list.length ? list : undefined });
  };
  const setMode = (mode) => {
    const names = ch.chart.entities || (ch.chart.entity ? [ch.chart.entity] : []);
    if (mode === "line_grow") patchChart({ mode, entity: names[0] || ch.chart.highlight || "India", entities: undefined });
    else patchChart({ mode, entities: names.length ? names : undefined, entity: undefined });
  };

  return (
    <>
      <PageHeader
        title={ep.title}
        sub={<><Chip tone={tone} style={{ verticalAlign: 1 }}>{label}</Chip>{" "}
          {dirty ? <Chip tone="warn" plain>Unsaved changes</Chip> : <span>All changes saved</span>}</>}
      >
        <Btn kind="ghost" icon="left" onClick={onBack}>All episodes</Btn>
        {saved.has_video && <Btn icon="play" onClick={() => setWatch(true)}>Watch</Btn>}
        <Btn disabled={!dirty || busy} onClick={() => save(false)}>Save</Btn>
        {live
          ? <Btn kind="danger" disabled={!saved.build?.stoppable} onClick={stop}
                 title={saved.build?.stoppable ? undefined : "Started from the command line; stop it there"}>
              Stop rendering
            </Btn>
          : <Btn kind="primary" icon="play" disabled={busy || !chapters.length} onClick={render}>
              {saved.has_video && !saved.video_stale && !dirty ? "Render again" : "Render a draft"}
            </Btn>}
      </PageHeader>

      <LongformLive ep={saved} onStop={stop} />
      {!live && build.status === "failed" && (
        <Banner tone="bad" role="alert" title="The last render failed">
          <details><summary style={{ cursor: "pointer" }}>Show details</summary>
            <code className="num" style={{ fontSize: 12 }}>{build.error}</code></details>
        </Banner>
      )}
      {!live && build.status === "stopped" && (
        <Banner title="The last render was stopped before it finished">
          Finished chapters are kept. Render again to pick up where it left off.
        </Banner>
      )}

      <div className="lf-editor">
        <section className="card lf-chapters" aria-label="Chapters">
          <div className="rowf" style={{ padding: "4px 8px 10px" }}>
            <h2>Chapters</h2><span className="num muted" style={{ fontSize: 12.5 }}>{chapters.length}</span>
            <span className="spacer" />
            <Btn kind="ghost" size="sm" icon="plus" iconOnly="Add a chapter" onClick={addChapter} />
          </div>
          <div className="stack" style={{ gap: 2 }}>
            {chapters.map((c, i) => {
              const s = saved.chapters.find((x) => x.id === c.id);
              return (
                <button key={c.id} type="button" className={"ch" + (i === sel ? " on" : "")}
                        aria-current={i === sel ? "true" : undefined} onClick={() => setSel(i)}>
                  <span className="n">{i + 1}</span>
                  <span className="t">{c.heading || c.id}</span>
                  {c.check && <span className="flag" role="img" aria-label="Has a line to fact-check" />}
                  {s?.rendered && s.narration === c.narration &&
                    <span className="ok" role="img" aria-label="Rendered" />}
                  <span className="d">{clock(secsOf(c))}</span>
                </button>
              );
            })}
          </div>
          {chapters.length === 0 && <Empty icon="topics" title="No chapters yet">Add the first one.</Empty>}
          <p className="faint" style={{ fontSize: 12.5, padding: "10px 8px 0" }}>
            Yellow dot: a line to fact-check. Green dot: rendered and unchanged.
          </p>
        </section>

        {ch ? (
          <section className="card stack lf-chapter" style={{ gap: 16 }} aria-label={`Chapter ${sel + 1}: ${ch.heading}`}>
            <div className="rowf">
              <Chip plain tone="go" className="num">{sel + 1}</Chip>
              <label className="field" style={{ flex: "1 1 240px" }}>
                <span className="sr">Chapter heading</span>
                <input className="input" type="text" value={ch.heading || ""} style={{ fontSize: 17, fontWeight: 600 }}
                       onChange={(e) => patchCh({ heading: e.target.value })} />
              </label>
              <Btn kind="ghost" size="sm" iconOnly="Move chapter up" icon="left" disabled={sel === 0}
                   onClick={() => move(-1)} style={{ transform: "rotate(90deg)" }} />
              <Btn kind="ghost" size="sm" iconOnly="Move chapter down" icon="right" disabled={sel === chapters.length - 1}
                   onClick={() => move(1)} style={{ transform: "rotate(90deg)" }} />
              <Btn kind="ghost" size="sm" icon="trash" iconOnly="Remove this chapter" onClick={removeChapter} />
            </div>

            <div className="lf-wide" aria-label="Chapter preview">
              {savedCh?.rendered
                ? <video key={`${ch.id}:${build.finished_at || ""}`} controls preload="metadata" playsInline
                         src={`/api/longform/${epKey}/chapter/${ch.id}/video`} />
                : <span style={{ fontSize: 13, padding: 16 }}>
                    This chapter has not been rendered yet. Render a draft to see the chart with its narration.
                  </span>}
            </div>

            <div className="rowf" style={{ alignItems: "flex-end" }}>
              <label className="field" style={{ flex: "1 1 150px" }}>Chart
                <Select value={ch.chart.mode} onChange={setMode} options={MODES} />
              </label>
              <label className="field" style={{ flex: "2 1 240px" }}>What it measures
                <Select value={ch.chart.code} onChange={(code) => patchChart({ code })}
                        options={[...meta.indicators.map((i) => ({ value: i.code, label: i.label })),
                          ...(meta.indicators.some((i) => i.code === ch.chart.code)
                            ? [] : [{ value: ch.chart.code, label: ch.chart.code }])]} />
              </label>
              <label className="field" style={{ flex: "0 1 110px" }}>From
                <input className="input num" type="number" value={ch.chart.year_min ?? ""}
                       onChange={(e) => patchChart({ year_min: e.target.value ? Number(e.target.value) : undefined })} />
              </label>
              <label className="field" style={{ flex: "0 1 110px" }}>To
                <input className="input num" type="number" value={ch.chart.year_max ?? ""}
                       onChange={(e) => patchChart({ year_max: e.target.value ? Number(e.target.value) : undefined })} />
              </label>
            </div>
            <div className="rowf" style={{ alignItems: "flex-end" }}>
              <label className="field" style={{ flex: "2 1 260px" }}>
                {ch.chart.mode === "line_grow" ? "Country" : ch.chart.mode === "line_multi"
                  ? "Countries, separated by commas" : "Countries (leave empty for the biggest)"}
                <input className="input" type="text" value={countries} onChange={(e) => setCountries(e.target.value)} />
              </label>
              {(ch.chart.mode === "bar_race" || ch.chart.mode === "bump_race") && (
                <>
                  <label className="field" style={{ flex: "1 1 140px" }}>Highlight
                    <input className="input" type="text" value={ch.chart.highlight || ""} placeholder="none"
                           onChange={(e) => patchChart({ highlight: e.target.value || undefined })} />
                  </label>
                  <label className="field" style={{ flex: "0 1 110px" }}>How many
                    <input className="input num" type="number" min="3" max="15" value={ch.chart.top_n ?? 10}
                           onChange={(e) => patchChart({ top_n: Number(e.target.value) || 10 })} />
                  </label>
                </>
              )}
            </div>

            <label className="field">What the narrator says
              <textarea className="input lf-narration" rows="8" value={ch.narration || ""}
                        onChange={(e) => patchCh({ narration: e.target.value })} />
              <span className="rowf" style={{ justifyContent: "space-between", fontSize: 12.5 }}>
                <span className="faint">The chart runs for exactly as long as this takes to say.</span>
                <span className="num muted">{wordCount(ch.narration)} words · about {clock(secsOf(ch))}</span>
              </span>
            </label>
            <div className="rowf">
              <Btn size="sm" icon="play" disabled={busy || !wordCount(ch.narration)} onClick={listen}>
                Listen to this chapter
              </Btn>
              {audio && <audio key={audio} src={audio} controls autoPlay style={{ flex: "1 1 240px", height: 36 }}
                               onError={() => toast("The narration could not be generated. Check the connection.", true)} />}
            </div>

            <label className="field">Line to fact-check (history that is not in the chart data)
              <input className="input" type="text" value={ch.check || ""} placeholder="Nothing to check"
                     onChange={(e) => patchCh({ check: e.target.value || undefined })} />
            </label>

            {dirty && JSON.stringify(ch.chart) !== JSON.stringify(savedCh?.chart)
              ? <p className="faint" style={{ fontSize: 12.5 }}>Save to see the figures for the changed chart.</p>
              : <Figures epKey={epKey} chapterId={ch.id} version={JSON.stringify(savedCh?.chart)} />}
          </section>
        ) : <section className="card lf-chapter"><Empty icon="topics" title="Add a chapter to start the script" /></section>}

        <aside className="lf-side" aria-label="Episode">
          <section className="card">
            <div className="card-head"><h2>Length</h2><span className="spacer" />
              <span className="num">{clock(totalSecs)} of {clock(target)}</span></div>
            <Bar pct={(totalSecs / target) * 100}
                 color={totalSecs > target * 1.15 || totalSecs < target * 0.8 ? "var(--warn)" : undefined} />
            <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>
              {totalWords} words.{" "}
              {totalSecs < target * 0.8
                ? `About ${Math.round(((target - totalSecs) / 60) * WPM / 10) * 10} more would reach the target.`
                : totalSecs > target * 1.15 ? "Longer than the target." : "On target."}
            </p>
            <label className="field" style={{ marginTop: 10 }}>Target length, minutes
              <input className="input num" type="number" min="1" max="30" value={ep.target_minutes ?? 5}
                     onChange={(e) => patch({ target_minutes: Number(e.target.value) || 5 })} />
            </label>
          </section>

          <section className="card stack">
            <h2>Voice and music</h2>
            <label className="field">Narrator
              <Select value={ep.voice || meta.voices[0].id} onChange={(voice) => patch({ voice })}
                      options={meta.voices.map((v) => ({ value: v.id, label: v.label }))} />
            </label>
            <label className="field">Pace
              <Select value={ep.voice_rate || "+0%"} onChange={(voice_rate) => patch({ voice_rate })} options={PACES} />
            </label>
            <label className="field">Music mood
              <Select value={ep.music_mood || "majestic"} onChange={(music_mood) => patch({ music_mood })}
                      options={MOODS.map((m) => ({ value: m, label: m[0].toUpperCase() + m.slice(1) }))} />
            </label>
            <p className="faint" style={{ fontSize: 12.5 }}>
              Music plays quietly under the voice. Changing the narrator or pace re-renders every chapter.
            </p>
          </section>

          <section className="card">
            <div className="card-head"><h2>Before you publish</h2></div>
            <ul className="stack" style={{ margin: 0, padding: 0, listStyle: "none", gap: 10, fontSize: 13.5 }}>
              <li className="rowf"><span className={"dot " + (checks ? "warn" : "")} />
                <span style={{ flex: 1 }}>{checks ? `${plural(checks, "line")} to fact-check` : "No lines left to fact-check"}</span></li>
              <li>
                <label className="rowf" style={{ flexWrap: "nowrap", cursor: "pointer" }}>
                  <input className="check" type="checkbox" checked={!!ep.reviewed} style={{ flex: "none" }}
                         onChange={(e) => patch({ reviewed: e.target.checked })} />
                  <span>I have read and checked the script</span>
                </label></li>
              <li className="rowf">
                <span className={"dot " + (saved.has_video && !saved.video_stale && !dirty ? "" : "idle")} />
                <span style={{ flex: 1 }}>
                  {saved.has_video && !saved.video_stale && !dirty ? `Rendered, ${clock(build.secs || totalSecs)}`
                    : saved.has_video ? "Edited since the last render" : "Not rendered yet"}
                </span></li>
            </ul>
            {saved.has_video && (
              <div className="rowf" style={{ marginTop: 14 }}>
                <Btn size="sm" icon="folder" onClick={() => onOpen(`output/longform/${epKey}`)}>Open the folder</Btn>
              </div>
            )}
            <p className="faint" style={{ fontSize: 12.5, marginTop: 12 }}>
              The folder holds the video, a subtitle file, the title and a description with chapter timestamps.
              Uploading long-form videos is done by hand for now.
            </p>
          </section>
        </aside>
      </div>

      {watch && <Player src={`/api/longform/${epKey}/video?t=${build.finished_at || ""}`} title={ep.title}
                        onClose={() => setWatch(null)} />}
    </>
  );
}

/* ───────────────────────────── page ───────────────────────────── */

export default function LongformPage({ toast, confirm, promptText, onOpen }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [watch, setWatch] = useState(null);

  const load = useCallback(() => api("/api/longform").then(setData).catch((e) => toast(e.message, true)), [toast]);
  useEffect(() => { if (!open) load(); }, [open, load]);
  const building = data?.building;
  useEffect(() => {
    if (!building || open) return undefined;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [building, open, load]);

  const create = async (idea) => {
    const title = idea ? idea.title : await promptText({
      title: "New episode", message: "Give it a working title. You can change it later.",
      input: { label: "Title", placeholder: "e.g. Who Powers the World?" }, confirmLabel: "Create episode",
    });
    if (!title) return;
    try {
      const r = await api("/api/longform", { title, series: idea?.series });
      setOpen(r.key);
    } catch (e) {
      toast(e.message, true);
    }
  };

  if (!data) return <SkeletonRows rows={6} />;
  if (open) {
    return <Editor epKey={open} meta={data} onBack={() => setOpen(null)} toast={toast} confirm={confirm} onOpen={onOpen} />;
  }
  return (
    <>
      <EpisodeList data={data} onOpen={setOpen} onCreate={create} onWatch={setWatch} />
      {watch && <Player src={`/api/longform/${watch.key}/video`} title={watch.title} onClose={() => setWatch(null)} />}
    </>
  );
}
