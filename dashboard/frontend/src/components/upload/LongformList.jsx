import { Banner, Bar, Btn, Chip, Empty, PlaylistChip, fmtDuration, fmtWhen } from "../../ui.jsx";

/* Long-form episodes on the Upload page. Each one goes up on its own (no
   batch): Private, with thumbnail, chapters, subtitles and playlist, then a
   switch to Public in YouTube Studio, the same as the Shorts. */

const STAGE = {
  starting: "Starting", authorising: "Signing in to YouTube", uploading: "Uploading the video",
  thumbnail: "Setting the thumbnail", subtitles: "Adding subtitles", playlist: "Adding to the playlist",
  recording: "Recording the upload", done: "Done",
};

const open = (url) => window.open(url, "_blank", "noopener");

function EpisodeCard({ ep, onUpload, onOpen }) {
  const up = ep.upload || {};
  const run = up.run;
  const blocked = (up.checks || []).filter((c) => !c.ok);
  const secs = ep.build?.secs || ep.secs;

  let status;
  if (run?.state === "running") {
    status = (
      <div className="stack" style={{ gap: 6, marginTop: 8 }}>
        <div className="rowf" style={{ fontSize: 13 }}>
          <span style={{ flex: 1 }}>{STAGE[run.stage] || run.stage}</span>
          <span className="num faint">{run.pct || 0}%</span>
        </div>
        <Bar pct={run.pct || 0} running />
      </div>
    );
  } else if (up.uploaded) {
    status = (
      <p className="muted">
        Uploaded {fmtWhen(up.uploaded_at)}. It stays Private until you switch it to Public in Studio.
      </p>
    );
  } else if (blocked.length) {
    status = (
      <ul className="faint" style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5 }}>
        {blocked.map((c) => <li key={c.name}>{c.detail}</li>)}
      </ul>
    );
  } else {
    status = <p className="muted">Ready: thumbnail, chapters, subtitles and playlist go up with it.</p>;
  }

  return (
    <article className="card q-card" style={{ cursor: "default" }}>
      <div className="rowf" style={{ alignItems: "flex-start", gap: 14 }}>
        {ep.has_video
          ? <img src={`/api/longform/${ep.key}/thumbnail?t=${ep.build?.finished_at || ""}`} alt=""
                 loading="lazy" style={{ width: 128, height: 72, objectFit: "cover", borderRadius: 8,
                                         flex: "none", border: "1px solid var(--line-2)" }} />
          : <div className="thumb" style={{ width: 128, height: 72, borderRadius: 8 }} />}
        <div className="q-body" style={{ minWidth: 0 }}>
          <h2>{ep.yt_title || ep.title}</h2>
          <div className="rowf" style={{ marginTop: 6 }}>
            <PlaylistChip series={ep.series} name={ep.playlist} />
            {ep.has_video && secs != null && (
              <span className="muted num" style={{ fontSize: 12.5 }}>{fmtDuration(secs)}</span>
            )}
            <span className="muted" style={{ fontSize: 12.5 }}>{ep.chapters.length} chapters</span>
            {up.uploaded && <Chip tone="go">Uploaded</Chip>}
          </div>
          {status}
          {run?.state === "failed" && (
            <div style={{ marginTop: 8 }}>
              <Banner tone="bad" role="alert" title="The upload failed">{run.error}</Banner>
            </div>
          )}
        </div>
      </div>
      <div className="rowf" style={{ gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
        {ep.has_video && (
          <Btn kind="ghost" size="sm" icon="play" onClick={() => open(`/api/longform/${ep.key}/video`)}>Watch</Btn>
        )}
        {ep.has_video && (
          <Btn kind="ghost" size="sm" icon="folder" onClick={() => onOpen(`output/longform/${ep.key}`)}>Folder</Btn>
        )}
        {up.uploaded ? (
          <>
            {up.url && <Btn size="sm" icon="youtube" onClick={() => open(up.url)}>Watch on YouTube</Btn>}
            {up.studio && <Btn size="sm" kind="primary" icon="external" onClick={() => open(up.studio)}>Open in Studio</Btn>}
          </>
        ) : run?.state !== "running" && (
          <Btn size="sm" kind="primary" icon="upload" disabled={blocked.length > 0}
               title={blocked.map((c) => c.detail).join(" · ") || undefined} onClick={() => onUpload(ep)}>
            {run?.state === "failed" ? "Try again" : "Upload"}
          </Btn>
        )}
      </div>
    </article>
  );
}

export default function LongformList({ episodes, onUpload, onOpen }) {
  if (episodes == null) return <div className="card"><Empty icon="upload" title="Loading episodes" /></div>;
  if (!episodes.length) {
    return (
      <div className="card">
        <Empty icon="upload" title="No long-form episodes yet">
          Episodes are written and rendered on the Long-form page, then uploaded from here.
        </Empty>
      </div>
    );
  }
  // Ready first, then in progress, then already uploaded.
  const rank = (e) => (e.upload?.run?.state === "running" ? 0 : e.upload?.uploaded ? 3
    : (e.upload?.checks || []).every((c) => c.ok) ? 1 : 2);
  return (
    <>
      {[...episodes].sort((a, b) => rank(a) - rank(b)).map((ep) => (
        <EpisodeCard key={ep.key} ep={ep} onUpload={onUpload} onOpen={onOpen} />
      ))}
      <p className="faint q-note">
        Long-form episodes upload one at a time, straight away, and arrive as Private like the Shorts.
        Each uses 2,102 API units, a little more than a Short because of the subtitles.
      </p>
    </>
  );
}
