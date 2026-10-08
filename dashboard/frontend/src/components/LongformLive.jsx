import { Bar, Btn } from "../ui.jsx";
import { Dial } from "./LiveRun.jsx";
import "../screens/longform.css";

/* Overall percent for an episode build. Chapters are nearly all of the work;
   joining and mixing take the last few percent. */
export function buildPct(build) {
  const total = Math.max(1, build?.total || 1);
  if (build?.stage === "mixing") return 97;
  if (build?.stage === "assembling") return 94;
  return Math.round(((build?.index || 0) / total) * 92);
}

export function buildDoing(build) {
  if (build?.stage === "mixing") return "Mixing music under the voice";
  if (build?.stage === "assembling") return "Joining the chapters";
  return `Chapter ${(build?.index || 0) + 1} of ${build?.total || "?"}: ${build?.heading || build?.chapter || "starting"}`;
}

/* The one "a long-form episode is rendering" card, shown on Overview, on the
   episode list and in the editor, so progress looks the same everywhere. It
   uses the same dial as the Shorts render card. */
export default function LongformLive({ ep, onOpen, onStop }) {
  const build = ep?.build;
  if (!build?.live) return null;
  const pct = buildPct(build);
  const total = build.total || ep.chapters.length;
  const at = build.stage === "chapter" ? build.index || 0 : total;

  return (
    <section className="card" style={{ borderColor: "rgba(200,245,96,.4)" }} aria-label="Long-form render in progress">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <span className="dot live" aria-hidden="true" />
        <h2>Rendering a long-form episode</h2>
        <span className="muted" style={{ fontSize: 13, minWidth: 0 }}>{ep.title}</span>
        <span className="spacer" />
        {onOpen && <Btn size="sm" onClick={onOpen}>Open the editor</Btn>}
        {onStop && (
          <Btn kind="danger" size="sm" disabled={!build.stoppable} onClick={onStop}
               title={build.stoppable ? undefined : "Started from the command line; stop it there"}>
            Stop
          </Btn>
        )}
      </div>
      <div className="rowf" style={{ flexWrap: "nowrap", gap: 20 }}>
        <Dial pct={pct} running size="sm" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 550 }}>{buildDoing(build)}</div>
          <Bar pct={pct} running height={8} style={{ margin: "10px 0" }} />
          <div className="lf-pips" role="img" aria-label={`${at} of ${total} chapters done`}>
            {ep.chapters.map((c, i) => (
              <i key={c.id} className={i < at ? "done" : i === at ? "now" : ""} title={c.heading || c.id} />
            ))}
          </div>
        </div>
      </div>
      {build.log?.length > 0 && <pre className="lf-log">{build.log.join("\n")}</pre>}
    </section>
  );
}
