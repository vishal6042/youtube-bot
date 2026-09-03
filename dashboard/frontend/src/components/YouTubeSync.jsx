import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

const fmt = (n) =>
  n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
  : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);

/** Local-vs-live YouTube sync: counts come in, copy edits go out. */
export default function YouTubeSync({ toast, confirm, onSynced }) {
  const [stats, setStats] = useState(null);   // stored snapshot (free)
  const [sync, setSync] = useState(null);     // live diff after a pull
  const [busy, setBusy] = useState(false);

  const loadStored = useCallback(async () => {
    try { setStats(await api("/api/yt/stats")); } catch { /* DB down — panel still renders */ }
  }, []);
  useEffect(() => { loadStored(); }, [loadStored]);

  const pull = async () => {
    setBusy(true);
    try {
      const r = await api("/api/yt/sync", {});
      setSync(r);
      loadStored();
      toast(r.adopted?.length
        ? `✅ Synced — updated local copy from YouTube: ${r.adopted.join(", ")}`
        : `✅ Synced from YouTube (${r.units_spent} quota units)`);
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const pushables = sync
    ? sync.playlists.filter((p) => p.found && p.differs).map((p) => p.series)
    : [];
  const channelDiffers = sync?.channel?.differs;

  const push = async () => {
    const items = [];
    if (channelDiffers) items.push({ title: "Channel description", meta: "channels.update" });
    sync.playlists.filter((p) => p.found && p.differs).forEach((p) =>
      items.push({ title: p.name, meta: p.remote_title !== p.name ? `rename from “${p.remote_title}”` : "description" }));
    const ok = await confirm({
      title: "Push these edits to YouTube?",
      message: `${items.length} item${items.length === 1 ? "" : "s"} will be updated on the `
             + `live channel (50 quota units each). This changes what viewers see.`,
      items,
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api("/api/yt/push", { channel: !!channelDiffers, playlists: pushables });
      if (r.errors?.length) toast(`⚠ ${r.errors.join(" · ")}`, true);
      else toast(`✅ Pushed to YouTube: ${r.applied.join(", ")}`);
      await pull();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const ch = sync?.channel || stats?.channel;
  const priv = sync?.private || [];

  return (
    <section className="panel">
      <div className="panel-title">
        YOUTUBE SYNC
        <span className="muted"> — live channel data · edits push on your confirm</span>
      </div>

      {ch && (
        <div className="yt-stats">
          <div className="yt-stat"><b>{fmt(ch.subscribers)}</b><span>subscribers</span></div>
          <div className="yt-stat"><b>{fmt(ch.views)}</b><span>total views</span></div>
          <div className="yt-stat"><b>{fmt(ch.video_count)}</b><span>videos</span></div>
          <div className="yt-stat muted-stat">
            <b>{(sync?.fetched_at || stats?.channel?.fetched_at || "").replace("T", " ") || "never"}</b>
            <span>last synced</span>
          </div>
        </div>
      )}

      <div className="yt-actions">
        <button className="btn" disabled={busy} onClick={pull}>
          {busy ? "…" : "⟲ SYNC FROM YOUTUBE"}
        </button>
        {sync && (channelDiffers || pushables.length > 0) && (
          <button className="btn btn-primary" disabled={busy} onClick={push}>
            ⬆ PUSH {(channelDiffers ? 1 : 0) + pushables.length} CHANGE{(channelDiffers ? 1 : 0) + pushables.length === 1 ? "" : "S"} TO YOUTUBE
          </button>
        )}
        {sync && !channelDiffers && pushables.length === 0 && (
          <span className="muted">✓ local copy matches YouTube</span>
        )}
      </div>

      {priv.length > 0 && (
        <div className="yt-private">
          ⚠ {priv.length} uploaded video{priv.length === 1 ? " is" : "s are"} still
          <b> Private</b> on YouTube — nobody can see them:
          <ul>
            {priv.map((v) => (
              <li key={v.video_id}>
                <a href={`https://studio.youtube.com/video/${v.video_id}/edit`}
                   target="_blank" rel="noreferrer">{v.title || v.topic_key}</a>
                <span className="muted"> — flip to Public in Studio</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sync && (
        <div className="yt-diff">
          <div className={`yt-row ${channelDiffers ? "differs" : ""}`}>
            <span className="yt-row-name">Channel description</span>
            <span className="muted">
              {channelDiffers ? "✎ local edit — ready to push" : "✓ in sync"}
            </span>
          </div>
          {sync.playlists.map((p) => (
            <div className={`yt-row ${p.differs ? "differs" : ""}`} key={p.series}>
              <span className="yt-row-name">{p.name}</span>
              <span className="muted">
                {!p.found ? "— not found on YouTube"
                  : p.differs ? "✎ local edit — ready to push"
                  : `✓ in sync · ${p.item_count ?? "?"} videos`}
              </span>
            </div>
          ))}
        </div>
      )}

      {sync?.videos?.length > 0 && (
        <div className="yt-top">
          <div className="muted" style={{ marginBottom: 6 }}>TOP VIDEOS RIGHT NOW</div>
          {sync.videos.slice(0, 5).map((v) => (
            <div className="yt-vrow" key={v.video_id}>
              <span className="yt-vtitle">{v.title || v.topic_key}</span>
              <span className="muted">{fmt(v.views)} views · {fmt(v.likes)} likes</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
