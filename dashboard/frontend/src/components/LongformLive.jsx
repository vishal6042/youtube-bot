import { useEffect, useState } from "react";
import { Bar, Btn, Icon, Stat } from "../ui.jsx";
import { Dial } from "./LiveRun.jsx";
import "../screens/longform.css";

const clock = (secs) => {
  const s = Math.max(0, Math.round(secs || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const since = (iso) => (iso ? Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000) : null);

/* How far through the chapter being rendered: voice and combine are seconds,
   the chart is nearly all of it, so the chart's frame count carries the bar. */
function chapterShare(build) {
  if (build?.stage !== "chapter") return 0;
  if (build.sub === "combine") return 0.96;
  if (build.sub === "chart" && build.frames) return 0.04 + 0.9 * (build.frame / build.frames);
  return build.sub === "chart" ? 0.04 : 0.01;
}

/* Overall percent for an episode build. Chapters are nearly all of the work;
   joining and mixing take the last few percent. */
export function buildPct(build) {
  const total = Math.max(1, build?.total || 1);
  if (build?.stage === "mixing") return 97;
  if (build?.stage === "assembling") return 94;
  return Math.round((((build?.index || 0) + chapterShare(build)) / total) * 92);
}

const SUB_DOING = { voice: "recording the voice", chart: "drawing the chart", combine: "combining voice and chart" };

export function buildDoing(build) {
  if (build?.stage === "mixing") return "Mixing music under the voice";
  if (build?.stage === "assembling") return "Joining the chapters";
  return `Chapter ${(build?.index || 0) + 1} of ${build?.total || "?"} · ${build?.heading || build?.chapter || "starting"}`
    + (build?.sub ? ` · ${SUB_DOING[build.sub]}` : "");
}

/* The three sub-stages of the chapter being rendered. */
function Stages({ build }) {
  const order = ["voice", "chart", "combine"];
  const at = order.indexOf(build.sub || "voice");
  const chartPct = build.frames ? Math.round((build.frame / build.frames) * 100) : 0;
  const cell = (i, name, running, done, waiting, pct) => (
    <div className={"rd-st" + (i === at ? " on" : "")}>
      <span><b>{name}</b><em className="num">{i < at ? done : i === at ? running : waiting}</em></span>
      <Bar pct={i < at ? 100 : i === at ? pct : 0} running={i === at} height={5} />
    </div>
  );
  return (
    <div className="rd-stages">
      {cell(0, "Voice", "recording", build.voice_secs ? `done · ${clock(build.voice_secs)}` : "done", "waiting", 60)}
      {cell(1, "Chart",
        build.frames ? `frame ${build.frame.toLocaleString("en-US")} of ${build.frames.toLocaleString("en-US")} · ${chartPct}%`
          : "loading the data",
        "done", "waiting", build.frames ? chartPct : 4)}
      {cell(2, "Combine", "joining voice and chart", "done", "waiting", 60)}
    </div>
  );
}

/* The one "a long-form episode is rendering" card, shown on Overview (compact),
   and in full in the episode editor: elapsed time, time left, and a row per
   chapter with the working chapter opened into its voice / chart / combine
   stages. It uses the same dial as the Shorts render card. */
export default function LongformLive({ ep, onOpen, onStop, compact }) {
  const build = ep?.build;
  const live = !!build?.live;
  const [, tick] = useState(0);
  // Elapsed time has to move between the dashboard's 3-4 second polls.
  useEffect(() => {
    if (!live) return undefined;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [live]);
  if (!live) return null;

  const pct = buildPct(build);
  const chapters = ep.chapters;
  const total = build.total || chapters.length;
  const inChapters = build.stage === "chapter";
  const at = inChapters ? build.index || 0 : total;
  const elapsed = since(build.started_at);

  // Time left: what the chapters rendered so far actually took, applied to the
  // rest. Nothing is claimed until at least one chapter has a measured time.
  const tooks = chapters.map((c) => c.took).filter((t) => t > 0);
  const avg = tooks.length ? tooks.reduce((a, b) => a + b, 0) / tooks.length : null;
  const todo = chapters.filter((_, i) => i > at).length;
  const left = avg == null ? null
    : inChapters ? avg * (todo + (1 - chapterShare(build))) + 25 : 20;
  const leftText = left == null ? "" : left < 60 ? "under 1 min" : `${Math.round(left / 60)} min`;

  const head = (
    <div className="rowf rd-head">
      <Dial pct={pct} running size={compact ? "sm" : "md"} />
      <div style={{ flex: "1 1 260px", minWidth: 0 }}>
        <div className="rowf" style={{ gap: 8 }}>
          <span className="dot live" aria-hidden="true" />
          <span className="muted" style={{ fontSize: 13 }}>Rendering a long-form episode</span>
        </div>
        <h2 style={{ fontSize: compact ? 18 : 22, letterSpacing: "-.02em", marginTop: 4 }}>{ep.title}</h2>
        <div className="muted" style={{ fontSize: 13.5, marginTop: 4 }}>{buildDoing(build)}</div>
      </div>
      <div className="rd-figs">
        <Stat card={false} small label="Elapsed" value={elapsed == null ? "" : clock(elapsed)} />
        <Stat card={false} small label="About left" value={leftText || "working it out"} />
        <Stat card={false} small label="Chapters" value={`${Math.min(at, total)} of ${total}`} />
      </div>
      {onOpen && <Btn size="sm" onClick={onOpen}>Open the editor</Btn>}
      {onStop && (
        <Btn kind="danger" size="sm" disabled={!build.stoppable} onClick={onStop}
             title={build.stoppable ? undefined : "Started from the command line; stop it there"}>
          Stop
        </Btn>
      )}
    </div>
  );

  if (compact) {
    return (
      <section className="card stack" style={{ borderColor: "rgba(200,245,96,.4)", gap: 14 }}
               aria-label="Long-form render in progress">
        {head}
        <Bar pct={pct} running height={8} />
        {inChapters && <Stages build={build} />}
      </section>
    );
  }

  return (
    <section className="card stack" style={{ borderColor: "rgba(200,245,96,.4)", gap: 16 }}
             aria-label="Long-form render in progress">
      {head}
      <Bar pct={pct} running height={8} />

      <ol className="plain-list rd-rows" aria-label="Chapters">
        <li className="rd-row rd-cols" aria-hidden="true">
          <span /><span>Chapter</span><span>Voice · Chart · Combine</span><span style={{ textAlign: "right" }}>Took</span>
        </li>
        {chapters.map((c, i) => {
          const running = inChapters && i === at;
          // Position in this run, not "has a file from an earlier run": on a
          // re-render the later chapters still have old files but are not done.
          const done = i < at;
          return (
            <li key={c.id} className={"rd-row " + (running ? "run" : done ? "done" : "wait")}>
              <span className="rd-n">{done && !running ? <Icon name="check" /> : i + 1}</span>
              <div style={{ minWidth: 0 }}>
                {running || done ? <b>{c.heading || c.id}</b> : <span>{c.heading || c.id}</span>}
              </div>
              {running
                ? <Stages build={build} />
                : <div className="rd-mini" role="img" aria-label={done ? "All three stages done" : "Not started"}>
                    <i className={done ? "d" : ""} /><i className={done ? "d" : ""} /><i className={done ? "d" : ""} />
                  </div>}
              <span className={"num " + (done || running ? "muted" : "faint")} style={{ textAlign: "right", fontSize: 12.5 }}>
                {running ? clock(since(build.chapter_started_at) ?? 0)
                  : done ? (c.took ? clock(c.took) : "done") : "waiting"}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="rowf rd-foot">
        <span className="muted" style={{ fontSize: 13 }}>Then, for the whole episode:</span>
        {[["assembling", "Join the chapters"], ["mixing", "Mix music under the voice"]].map(([stage, label], i) => {
          const pos = build.stage === "mixing" ? 1 : build.stage === "assembling" ? 0 : -1;
          return (
            <span key={stage} className="rowf" style={{ gap: 8 }}>
              <span className={"dot " + (pos === i ? "live" : pos > i ? "" : "idle")} />{label}
            </span>
          );
        })}
        <span className="rowf" style={{ gap: 8 }}><span className="dot idle" />Subtitles, description and thumbnail</span>
      </div>
      {build.log?.length > 0 && (
        <details>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>Show the log</summary>
          <pre className="lf-log">{build.log.join("\n")}</pre>
        </details>
      )}
    </section>
  );
}
