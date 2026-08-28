import Chip from "./Chip.jsx";
import YouTubeIcon from "./YouTubeIcon.jsx";
import { STATE_CHIP } from "../api.js";

export default function EpisodeRow({ it, queueRank, working, onMark, onOpen, onRender, onLink, onWatch }) {
  const [cls, label] = STATE_CHIP[it.state];
  return (
    <div className="pl-row">
      <span className="ep">{String(it.episode).padStart(2, "0")}</span>
      <span className="title" title={it.key}>
        {it.url ? (
          <a href={it.url} target="_blank" rel="noopener noreferrer">{it.title}</a>
        ) : (
          it.title
        )}
        {queueRank && <Chip cls="chip-queue">🎯 NEXT #{queueRank}</Chip>}
      </span>
      <span className="pl-row-side">
        <Chip cls={cls}>{label}</Chip>
        {!working && it.state !== "missing" && (
          <button className="btn btn-mini" title="Watch here"
                  onClick={() => onWatch({ ...it, playlist: it.playlist })}>▶</button>
        )}
        {working ? (
          <span className="working">◉ IN PROGRESS</span>
        ) : it.state === "uploaded" ? (
          it.url ? (
            <a
              className="ep-yt"
              href={it.url}
              target="_blank"
              rel="noopener noreferrer"
              title="Watch on YouTube"
              aria-label="Watch on YouTube"
            >
              <YouTubeIcon />
            </a>
          ) : (
            <button className="btn btn-mini uh-addlink" onClick={() => onLink(it.key, it.title)}>
              + LINK
            </button>
          )
        ) : (
          <>
            {it.exported && (
              <button
                className="btn btn-mini"
                title="Open export folder"
                onClick={() => onOpen(it.exported)}
              >
                📂
              </button>
            )}
            {it.state === "ready" && (
              <button
                className="btn btn-mini btn-primary"
                onClick={() => onMark(it.key, it.title)}
              >
                ✅ MARK
              </button>
            )}
            <button className="btn btn-mini" onClick={() => onRender(it.key, it.title)}>
              ▶ {it.state === "missing" ? "RENDER" : "RE-RENDER"}
            </button>
          </>
        )}
      </span>
    </div>
  );
}
